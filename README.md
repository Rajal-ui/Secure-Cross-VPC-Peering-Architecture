# Secure Cross-VPC Peering Architecture

An AWS implementation of a secure, private communication channel between two isolated Virtual Private Clouds, simulating an **air-gapped financial reconciliation enclave**.

A private ingestion tier (VPC-A) ships synthetic transaction data over a VPC Peering connection to a Flask-based "AI Finance Controller" (VPC-B) that has **no Internet Gateway**, no public IPs, and no path to the internet. Administration is performed exclusively through a Bastion Host using SSH `ProxyJump`.

## Architecture

![Architecture Diagram](architecture%20diag.png)

```
Admin Workstation --(SSH:22)--> ewb-bastion (10.10.1.10)
                                     |
                                     +--(ProxyJump)--> ewb-app-a (10.10.2.10)
                                     |                       |
                                     |                       +--(HTTP:8080 over peering)--> ewb-app-b (10.20.1.10)
                                     |                                                          |
                                     +--(ProxyJump)----------------------------------------> Flask Controller /reconcile
```

## Network Topology

| Component | Name | CIDR / IP | Purpose |
| :-- | :-- | :-- | :-- |
| VPC-A (Ingestion) | `ewb-vpc-a` | `10.10.0.0/16` | Hosts Bastion and ingestion tier; has an IGW |
| Public Subnet | `ewb-a-public` | `10.10.1.0/24` | Hosts `ewb-bastion` |
| Private Subnet | `ewb-a-private` | `10.10.2.0/24` | Hosts `ewb-app-a` (no internet route) |
| VPC-B (Enclave) | `ewb-vpc-b` | `10.20.0.0/16` | Air-gapped; **no IGW attached** |
| Private Subnet | `ewb-b-private` | `10.20.1.0/24` | Hosts `ewb-app-b` |
| VPC Peering | `ewb-a-b-peer` | `pcx-XXXXXXXX` | Private, non-transitive link VPC-A ↔ VPC-B |
| Bastion | `ewb-bastion` | `10.10.1.10` + public IP | Secure jump host |
| Ingestion Tier | `ewb-app-a` | `10.10.2.10` | Synthetic data generator |
| Core Enclave | `ewb-app-b` | `10.20.1.10` | Flask reconciliation controller |

### Routing

| Route Table | Subnet | Routes |
| :-- | :-- | :-- |
| `ewb-rt-a-public` | `ewb-a-public` | `0.0.0.0/0` → `ewb-igw-a` ; `10.20.0.0/16` → `pcx-XXXXXXXX` |
| `ewb-rt-a-private` | `ewb-a-private` | `10.10.0.0/16` (local) ; `10.20.0.0/16` → `pcx-XXXXXXXX` |
| `ewb-rt-b-private` | `ewb-b-private` | `10.20.0.0/16` (local) ; `10.10.0.0/16` → `pcx-XXXXXXXX` |

### Security Groups

| Security Group | VPC | Inbound Rules |
| :-- | :-- | :-- |
| `ewb-sg-bastion` | VPC-A | TCP 22 from `Your_Public_IP/32` |
| `ewb-sg-app-a` | VPC-A | TCP 22 from `10.10.1.10/32` ; ICMP echo from `10.20.1.10/32` |
| `ewb-sg-app-b` | VPC-B | TCP 22 from `10.10.1.10/32` ; ICMP echo from `10.10.2.10/32` ; TCP 8080 from `10.10.2.10/32` |

All other inbound traffic is denied.

## Tech Stack

- **Cloud:** AWS (`ap-south-1` / Mumbai)
- **OS:** Amazon Linux 2023 (`t3.micro` × 3)
- **Runtime:** Python 3.9, Flask, `requests`
- **Networking:** VPC Peering, custom route tables, security groups, SSH `ProxyJump`
- **Offline bootstrapping:** wheels transferred via Bastion for internet-isolated instances

## Application Design

| Component | File | Function |
| :-- | :-- | :-- |
| App-A | `generator.py` | Generates synthetic transactions (UUID, amount, currency, merchant, timestamp) and `POST`s them to `http://10.20.1.10:8080/reconcile` every 3 seconds |
| App-B | `controller.py` | Flask `POST /reconcile` endpoint; responds `LLM Review` when `amount > 1000`, otherwise `Reconciled` |

These scripts are deployed directly onto the EC2 instances and are not stored in this repository.

## Deployment

Full step-by-step instructions (Console and AWS CLI) are documented in [SECURE_CROSS_VPC_PEERING_ARCHITECTURE_DOCUMENTATION.md](SECURE_CROSS_VPC_PEERING_ARCHITECTURE_DOCUMENTATION.md).

High-level flow:

1. Create VPC-A and VPC-B with non-overlapping CIDRs, plus subnets and route tables.
2. Attach an IGW to VPC-A only — VPC-B stays air-gapped.
3. Create least-privilege security groups.
4. Launch Bastion, App-A, App-B with static private IPs and the `ewb-lab` key pair.
5. Configure `~/.ssh/config` with `ProxyJump` through the Bastion.
6. Create and accept `ewb-a-b-peer`, then add peering routes to all three route tables.
7. Bootstrap `pip`, Flask, and `requests` offline via wheels transferred through the Bastion.
8. Deploy and run `controller.py` on App-B and `generator.py` on App-A.

## Usage

Start the controller (App-B):

```bash
nohup python3 ~/controller.py > ~/controller.log 2>&1 &
echo $! > ~/controller.pid
```

Start the generator (App-A):

```bash
nohup python3 ~/generator.py > ~/generator.log 2>&1 &
echo $! > ~/generator.pid
```

Monitor logs:

```bash
ssh ewb-app-a "tail -f ~/generator.log"
ssh ewb-app-b "tail -f ~/controller.log"
```

Stop applications:

```bash
ssh ewb-app-a "pkill -f generator.py"
ssh ewb-app-b "pkill -f controller.py"
```

## Validation

```bash
# Forward path
ssh ewb-app-a "ping -c 4 10.20.1.10"

# Reverse path
ssh ewb-app-b "ping -c 4 10.10.2.10"

# Private SSH through bastion
ssh ewb-app-b
```

Expected logs:

```
# generator.log (App-A)
[2026-10-24T14:44:30.046831+00:00] 64929ff8-... amount=257.91 -> HTTP 200

# controller.log (App-B)
[2026-10-24T14:43:35.927533+00:00] cb2a7491-... | Spotify | INR | 2003.61 => LLM Review
10.10.2.10 - - [24/Oct/2026 14:43:35] "POST /reconcile HTTP/1.1" 200 -
```

Transactions above 1000 are flagged `LLM Review`; all others are `Reconciled`. Every request returns HTTP 200 over the private peering link.

## Screenshots

Implementation evidence is available in the [`assets`](assets) directory, covering VPC creation, subnet and route table configuration, peering status, security groups, instance details, SSH sessions, and application logs.

## Key Learnings

- Air-gapping VPC-B by omitting an IGW enforces true network isolation.
- Bidirectional route table entries are mandatory for peering to work.
- Security groups can govern peered traffic down to source IP, port, and protocol.
- Offline package bootstrapping is achievable via Bastion-mediated wheel transfers.
- Bastion + `ProxyJump` provides auditable administration of private instances without exposing them.

## Future Enhancements

- TLS between App-A and App-B
- CloudWatch Logs for centralized logging
- IAM roles and Secrets Manager replacing long-term credentials
- Infrastructure as Code (Terraform / CloudFormation)
- SQS-based decoupling instead of direct HTTP
- Containerization of the generator and controller

## Cleanup

Delete resources in reverse order: terminate instances, delete the peering connection, security groups, route tables, subnets, IGW, VPCs, and finally the `ewb-lab` key pair.

## References

- [AWS VPC Peering](https://docs.aws.amazon.com/vpc/latest/peering/what-is-vpc-peering.html)
- [AWS Security Groups](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html)
- [Amazon EC2 User Guide](https://docs.aws.amazon.com/ec2/)
- [Flask Documentation](https://flask.palletsprojects.com/)
- [Python Requests](https://requests.readthedocs.io/)
- [Amazon Linux 2023](https://docs.aws.amazon.com/linux/al2023/)

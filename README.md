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
- **Security:** Network isolation, least-privilege security groups, optional shared-secret API key, strict input validation, request size limits

## Application Design

| Component | File | Function |
| :-- | :-- | :-- |
| App-A | [`files/generator.py`](files/generator.py) | Generates synthetic transactions (UUID, amount, currency, merchant, timestamp) and `POST`s them to `http://10.20.1.10:8080/reconcile` every 3 seconds |
| App-B | [`files/controller.py`](files/controller.py) | Flask `POST /reconcile` endpoint; responds `LLM Review` when `amount > 1000`, otherwise `Reconciled` |

Both scripts are tracked in the [`files`](files) directory and are copied to their respective EC2 instances during deployment. The controller requires Flask; the generator requires `requests`.

## Security Controls

- VPC-B has no Internet Gateway, no public IP addresses, and no NAT path. It is reachable only over the VPC peering connection.
- Security groups restrict ingress to the expected source `/32` addresses and ports; all other inbound traffic is denied.
- The controller enforces a 16 KB request body limit (`MAX_REQUEST_BYTES`) and validates every field before processing.
- Set a shared secret on both instances to require an `X-API-Key` header. Generate it once and use the same value on App-A and App-B:

  ```bash
  export RECONCILE_API_KEY="$(openssl rand -hex 32)"
  ```

  Without this variable, the endpoint relies on network isolation alone.
- Flask debug mode is disabled, and unexpected input returns `400`, `401`, or `413` instead of a traceback.
- Never commit `.pem`, credentials, or `.env` files. Keys, credential CSVs, and the `docs/` directory are ignored by Git.
- The generator uses a 5-second request timeout and catches network errors so a failed POST does not terminate the process.

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
8. Copy `files/controller.py` to App-B and `files/generator.py` to App-A, then start both processes.

## Usage

Generate a shared API key once and export the same value on both instances (optional, but recommended):

```bash
export RECONCILE_API_KEY="$(openssl rand -hex 32)"
```

Start the controller (App-B):

```bash
export RECONCILE_API_KEY="<shared-key>"
nohup python3 ~/controller.py > ~/controller.log 2>&1 &
echo $! > ~/controller.pid
```

Start the generator (App-A):

```bash
export RECONCILE_API_KEY="<shared-key>"
nohup python3 ~/generator.py > ~/generator.log 2>&1 &
echo $! > ~/generator.pid
```

`RECONCILE_URL` overrides the generator target, `INTERVAL_SECONDS` overrides the 3-second cadence, and `PORT` overrides the controller port.

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
Sent 64929ff8-... amount=257.91 status=200

# controller.log (App-B)
2026-10-24 14:43:35,927 INFO cb2a7491-... | amount=2003.61 | status=LLM Review | Amount exceeds the deterministic threshold of 1000.
10.10.2.10 - - [24/Oct/2026 14:43:35] "POST /reconcile HTTP/1.1" 200 -
```

Transactions above 1000 are flagged `LLM Review`; all others are `Reconciled`. Valid requests return HTTP 200 over the private peering link; unauthorized, invalid, and oversized requests return 401, 400, and 413 respectively.

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

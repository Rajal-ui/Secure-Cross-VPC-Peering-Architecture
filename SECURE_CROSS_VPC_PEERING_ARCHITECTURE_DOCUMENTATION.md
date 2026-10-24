# Secure Cross-VPC Peering Architecture: Air-Gapped Financial Reconciliation Enclave

## 1. Abstract

This project demonstrates the design and implementation of a secure, isolated financial reconciliation environment using AWS VPC Peering. It simulates a real-world banking/fintech use case where sensitive financial transaction processing must remain in an air-gapped enclave with no direct internet access, while still receiving transactional data from an ingestion layer. 

By leveraging private networking, bastion-based secure access, custom security groups, and route table configurations, a controlled and auditable path is established between two isolated VPCs to allow secure, internal communication for reconciliation workflows.

## 2. Objective

- To design and implement a secure cross-VPC communication architecture using AWS VPC Peering.
- To create an "Air-Gapped" Enclave (VPC-B) with no Internet Gateway to mimic strict data isolation.
- To deploy a Synthetic Data Generator on a private ingestion tier (VPC-A).
- To deploy a Flask-based "AI Finance Controller" on the air-gapped enclave (VPC-B) to perform mock deterministic reconciliation.
- To enforce least-privilege access using Security Groups and private IP routing.
- To securely administer private instances via a Bastion Host using SSH with ProxyJump.
- To validate end-to-end private communication over the peered network.

## 3. Problem Statement

In financial systems, transaction ingestion and core reconciliation often need to be segregated. Exposing the core reconciliation engine to the internet increases the attack surface. The goal of this project is to simulate this segregation by keeping the "Core Enclave" completely isolated from the internet, only allowing selective, internal communication from the ingestion layer over a privately routed VPC peering connection.

## 4. Architecture

### 4.1 High-Level Architecture

The architecture consists of two VPCs connected via a VPC Peering Connection. All application traffic flows privately using RFC1918 IP addresses. External access is only allowed to the Bastion Host via SSH from the administrator's public IP.

Admin Workstation --(SSH:22)--> ewb-bastion (10.10.1.10) --(ProxyJump)--> ewb-app-a (10.10.2.10) --(HTTP:8080 over peering)--> ewb-app-b (10.20.1.10)
                                                                                                                  | 
                                                                                                                Flask Controller - /reconcile

### 4.2 Network Topology

| Component | Name | CIDR/ IP | Purpose |
| :-- | :-- | :-- | :-- |
| VPC-A (Ingestion Layer) | `ewb-vpc-a` | `10.10.0.0/16` | Hosts Bastion and Ingestion Tier. Has an Internet Gateway for Bastion SSH access. |
| Public Subnet (VPC-A) | `ewb-a-public` | `10.10.1.0/24` | Hosts `ewb-bastion`. Routed to IGW for outbound/inbound admin access. |
| Private Subnet (VPC-A) | `ewb-a-private` | `10.10.2.0/24` | Hosts `ewb-app-a`. No direct internet route. |
| VPC-B (Air-Gapped Enclave) | `ewb-vpc-b` | `10.20.0.0/16` | Hosts Core Reconciliation Engine. NO Internet Gateway attached. |
| Private Subnet (VPC-B) | `ewb-b-private` | `10.20.1.0/24` | Hosts `ewb-app-b`. Completely isolated from the internet. |
| VPC Peering | `ewb-a-b-peer` | `pcx-XXXXXXXX` | Private, non-transitive connection between VPC-A and VPC-B. |
| Bastion Host | `ewb-bastion` | `10.10.1.10` + Public IP | Secure jump host to access private instances. |
| Ingestion Tier | `ewb-app-a` | `10.10.2.10` | Synthetic Data Generator. |
| Core Enclave | `ewb-app-b` | `10.20.1.10` | AI Finance Controller (Flask App). |

### 4.3 Routing Summary

| Route Table | Associated Subnet | Routes Configured |
| :-- | :-- | :-- |
| `ewb-rt-a-public` | `ewb-a-public` | `0.0.0.0/0` -> `ewb-igw-a` ; `10.20.0.0/16` -> `pcx-XXXXXXXX` |
| `ewb-rt-a-private` | `ewb-a-private` | `10.10.0.0/16` (Local) ; `10.20.0.0/16` -> `pcx-XXXXXXXX` |
| `ewb-rt-b-private` | `ewb-b-private` | `10.20.0.0/16` (Local) ; `10.10.0.0/16` -> `pcx-XXXXXXXX` |

### 4.4 Security Groups

| Security Group | VPC | Inbound Rules | Purpose |
| :-- | :-- | :-- | :-- |
| `ewb-sg-bastion` | VPC-A | TCP 22 from `Your_Public_IP/32` | Restricts SSH to the administrator only. |
| `ewb-sg-app-a` | VPC-A | TCP 22 from `10.10.1.10/32` (Bastion) ; ICMP Echo Request from `10.20.1.10/32` (App-B) | Allows bastion access and limited ICMP for connectivity testing. |
| `ewb-sg-app-b` | VPC-B | TCP 22 from `10.10.1.10/32` (Bastion) ; ICMP Echo Request from `10.10.2.10/32` (App-A) ; TCP 8080 from `10.10.2.10/32` (App-A) | Allows bastion SSH, ICMP and strictly allows App-A to POST to the Flask endpoint on port 8080. All other inbound traffic is denied. |

## 5. AWS Cloud Involvement & Working

| AWS Service/Feature | Usage | Working Explanation |
| :-- | :-- | :-- |
| **Amazon VPC** | `ewb-vpc-a`, `ewb-vpc-b` | Logical network isolation for each layer with custom CIDR blocks. |
| **Subnets** | Public/Private across AZ | Segregates internet-facing (Bastion) from strictly private resources. |
| **Internet Gateway (IGW)** | `ewb-igw-a` attached to VPC-A only | Provides outbound/inbound internet access solely for the Bastion Host. VPC-B remains without an IGW (air-gapped). |
| **Route Tables** | Custom route tables per subnet | Enforces traffic flow. Local routes allow intra-VPC, peering routes allow inter-VPC, and IGW route allows bastion internet access. |
| **VPC Peering** | `ewb-a-b-peer` (Active) | Establishes a private, encrypted-by-AWS-network routing path between VPC-A and VPC-B with no traversal over the public internet. |
| **Security Groups (Stateful)** | Bastion, App-A, App-B | Act as virtual firewalls. Stateful nature allows return traffic automatically. Only explicitly permitted sources/ports are allowed. |
| **EC2 (Amazon Linux 2023)** | 3 x `t3.micro` instances | Compute for Bastion, Synthetic Generator and Flask Controller. Launched with `ewb-lab` key pair. |
| **Key Pairs (EC2)** | `ewb-lab` | Used for all EC2 SSH authentication. |
| **SSH ProxyJump** | Local `~/.ssh/config` | Enables secure access to private instances by tunneling through the Bastion Host. |

## 6. Tech Stack

| Category | Technology | Purpose |
| :-- | :-- | :-- |
| Cloud Platform | AWS (ap-south-1) | Infrastructure provisioning and networking. |
| Operating System | Amazon Linux 2023 | Lightweight, secure OS for EC2 instances. |
| Scripting/Automation | Bash, PowerShell | SSH, file transfers, process management and deployment. |
| Programming Language | Python 3.9 | Application logic for generator and controller. |
| Web Framework | Flask | Lightweight REST API to receive transaction payloads on App-B. |
| HTTP Client | `requests` | Used by App-A to POST JSON to App-B over HTTP. |
| Networking Utilities | `ssh`, `scp`, `ping`, `curl`, `pkill`, `nohup` | Connectivity testing, secure transfer, and background execution. |
| Package Management (Offline) | `pip`, `get-pip.py`, wheels (`*.whl`) | Installed packages on internet-isolated instances via bastion-mediated transfer. |

## 7. Application Design

### 7.1 App-A: Synthetic Data Generator (`generator.py`)

**Location:** `ewb-app-a` (`10.10.2.10`) 

**Functionality:**
- Continuously generates synthetic financial transaction payloads in JSON format.
- Fields generated: `transaction_id` (UUID), `amount` (random float), `currency` (USD/EUR/GBP/INR), `merchant` (random list), `timestamp` (UTC ISO format).
- Sends each payload via `POST` to `http://10.20.1.10:8080/reconcile` every 3 seconds using the `requests` library.
- Logs request details with HTTP status code for visibility.

### 7.2 App-B: AI Finance Controller (`controller.py`)

**Location:** `ewb-app-b` (`10.20.1.10`) 

**Functionality:**
- Runs a Flask application listening on `0.0.0.0:8080`.
- Exposes REST endpoint: `POST /reconcile` to accept JSON transaction data.
- **Mock Deterministic Matching Logic:**
  - If `amount > 1000` -> status = `LLM Review` (routes to simulated bounded LLM review path)
  - Else -> status = `Reconciled`
- Prints/logs each transaction with merchant, currency, amount and final status to stdout (captured in `controller.log`).
- Returns a JSON response with `transaction_id`, `status`, `amount`, `currency` and `processed_at`.

## 8. End-to-End Workflow

| Step | Action | Description |
| :-- | :-- | :-- |
| 1 | **Network Setup** | Create VPC-A and VPC-B, subnets, IGW (VPC-A only), custom route tables. |
| 2 | **Security Hardening** | Create and configure Security Groups with least-privilege inbound rules. Add TCP 8080 allowance from App-A to App-B. |
| 3 | **Compute Provisioning** | Launch Bastion, App-A, App-B with `t3.micro` (Amazon Linux 2023) and static private IPs. Use `ewb-lab` key pair. |
| 4 | **Secure Access Setup** | Configure local `~/.ssh/config` with `ProxyJump` to access private instances via Bastion. |
| 5 | **VPC Peering** | Create `ewb-a-b-peer`, accept the request, and update all three route tables to route inter-VPC traffic via `pcx-XXXX`. |
| 6 | **Offline Package Preparation** | Use Bastion (internet access) to download `get-pip.py` (Python 3.9 compatible), `pip`, `flask`, `requests` and dependencies as wheels, transfer to App-A/App-B via SCP through Bastion. |
| 7 | **Application Deployment** | Install packages offline on App-A/App-B, create `generator.py` and `controller.py`, run controller on App-B and generator on App-A in background with `nohup`. |
| 8 | **Validation** | Test connectivity (`ping`), verify HTTP POSTs over peering, observe reconciliation logs. |

## 9. Working of the Project

1. **Initiation:** The user triggers traffic generation by running `generator.py` on `ewb-app-a`.
2. **Data Flow:** For every 3 seconds, App-A constructs a random transaction and performs `requests.post("http://10.20.1.10:8080/reconcile", json=payload)`.
3. **Routing:** Due to peering route on `ewb-rt-a-private`, packets are routed from `10.10.2.10` to `10.20.1.10` via the active VPC Peering connection.
4. **Ingress Control:** `ewb-sg-app-b` validates source IP `10.10.2.10/32` and allows TCP traffic on port 8080.
5. **Processing:** Flask on App-B parses the JSON, applies deterministic logic (`amount > 1000` -> `LLM Review`, else `Reconciled`), prints the outcome with timestamps, and responds with `HTTP 200 OK`.
6. **Visibility:** App-A logs the POST attempt with returned HTTP status. App-B logs the full reconciliation decision with merchant, currency, amount and status.
7. **Isolation:** App-B has no IGW, cannot reach the internet. All reconciliation happens strictly over the private peered network.

## 10. Application Usage

### 10.1 Start Controller (App-B)
```bash
nohup python3 ~/controller.py > ~/controller.log 2>&1 &
echo $! > ~/controller.pid
```
### 10.2 Start Generator (App-A)
```bash
nohup python3 ~/generator.py > ~/generator.log 2>&1 &
echo $! > ~/generator.pid
```
### 10.3 Monitor Live Output
#### From local machine
```bash
ssh ewb-app-b "tail -f ~/controller.log"
ssh ewb-app-a "tail -f ~/generator.log"
```
### 10.4 Stop Applications
```bash
ssh ewb-app-a "pkill -f generator.py"
ssh ewb-app-b "pkill -f controller.py"
```
## 11. Observed Output

During testing, the following was observed and validates correct working:

From generator.log (App-A):
```bash
[2026-10-24T14:44:30.046831+00:00] 64929ff8-... amount=257.91 -> HTTP 200
[2026-10-24T14:44:33.055497+00:00] 66521c62-... amount=1960.48 -> HTTP 200
[2026-10-24T14:44:36.062347+00:00] ec37eb9d-... amount=398.27 -> HTTP 200
```
From controller.log (App-B):
```bash
[2026-10-24T14:43:35.927533+00:00] cb2a7491-... | Spotify | INR | 2003.61 => LLM Review
10.10.2.10 - - [24/Oct/2026 14:43:35] "POST /reconcile HTTP/1.1" 200 -
[2026-10-24T14:44:05.993913+00:00] c0cc6221-... | Shell | INR | 979.68 => Reconciled
10.10.2.10 - - [24/Oct/2026 14:44:05] "POST /reconcile HTTP/1.1" 200 -
```
> Inference: Transactions with amount > 1000 are correctly flagged as LLM Review. Transactions with amount <= 1000 are correctly marked as Reconciled. All requests return HTTP 200 over the private VPC peering connection.

## 12. Key Learnings
- Network Segmentation: Achieved strict isolation by keeping VPC-B air-gapped with no IGW.
- Secure Remote Access: Implemented bastion-based administration using SSH ProxyJump.
- Private Inter-VPC Routing: Configured VPC Peering with accurate route table entries for bidirectional reachability.
- Least Privilege Security: Applied granular Security Group rules restricting traffic by source IP, port and protocol.
- Offline Package Deployment: Successfully bootstrapped pip and installed Python dependencies on internet-restricted EC2 instances using wheels transferred via Bastion.
- Practical Debugging: Resolved real issues like DNF timeouts (no internet), pip version mismatch (Python 3.9 vs newer get-pip.py), and Windows SCP pathing.
- End-to-End Validation: Verified connectivity with ping and validated application-level communication with HTTP logs.

## 13. Future Enhancements
- HTTPS/TLS: Terminate or tunnel traffic with TLS between components for encrypted application traffic.
- Logging & Monitoring: Integrate CloudWatch Logs/Agent to centralize generator.log and controller.log.
- IAM Roles: Replace long-term access patterns with least-privilege IAM roles where applicable.
- Secrets Management: Move any credentials to AWS Secrets Manager (currently lab uses key-based SSH only).
- Infrastructure as Code: Convert manual setup to Terraform/CloudFormation for repeatability.
- Queue-based Decoupling: Replace direct HTTP POST with SQS between App-A and App-B for better resilience.
- Containerization: Dockerize generator.py and controller.py for portability.
## 14. Conclusion
This project successfully implements a Secure Cross-VPC Peering Architecture demonstrating an Air-Gapped Financial Reconciliation Enclave. The ingestion tier and core enclave remain logically and network-wise segregated, with communication strictly controlled over a private peering link. The working Flask controller and synthetic generator validate the design by producing correct reconciliation decisions with full traceability in logs. This architecture closely mirrors industry practices for isolating sensitive financial processing workloads.
## 15. References
- AWS VPC Peering Documentation (https://docs.aws.amazon.com/vpc/latest/peering/what-is-vpc-peering.html)
- AWS VPC Security Groups (https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html)
- AWS EC2 User Guide (https://docs.aws.amazon.com/ec2/)
- Flask Documentation (https://flask.palletsprojects.com/)
- Python Requests Documentation (https://requests.readthedocs.io/)
- Amazon Linux 2023 Documentation (https://docs.aws.amazon.com/linux/al2023/)

## Appendix A: Project File Structure
```
Secure-Cross-VPC-Peering/
├── SECURE_CROSS_VPC_PEERING_ARCHITECTURE_DOCUMENTATION.md
├── architecture diag.png
└── README.md
```
(application scripts created on instances: generator.py, controller.py)
## Appendix B: Quick Verification Commands
### Network test 
```bash
ssh ewb-app-a "ping -c 4 10.20.1.10"
```
### Check processes
```bash
ssh ewb-app-a "ps aux | grep generator.py | grep -v grep"
ssh ewb-app-b "ps aux | grep controller.py | grep -v grep"
```
### Live monitoring
```bash
ssh ewb-app-a "tail -f ~/generator.log"
ssh ewb-app-b "tail -f ~/controller.log"
```
# Stop processes
```bash
ssh ewb-app-a "pkill -f generator.py"
ssh ewb-app-b "pkill -f controller.py"
```
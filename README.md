# Rwanda Real Estate Brokers Platform (RREBP)

Final Version Demo Video Link: [demolink](https://github.com/desparvis/rrebp)](https://drive.google.com/file/d/1hcDYk8K8tX_evZ4sHzldoox9A4PAXTq_/view?usp=drive_link) <br>
Github Link: [githublink](https://github.com/desparvis/rrebp)
Report Link: [reportlink](https://docs.google.com/document/d/1qpRgYgkxTaSbkCGwUvimn-oGjk2fBLov7tSdNG1WFLU/edit?tab=t.0)

## Description

Rwanda Real Estate Brokers Platform is a Web2 and Web3 application designed to improve transparency in the Rwandan real estate sector. It features standard Web2 capabilities such as authentication, content creation, editing, and deletion. These features allow users to register real estate associations, approve these associations, and locally register brokers alongside their property listings.

The platform also features Web3 capabilities, allowing verified brokers to be recorded on the blockchain to maintain an immutable, publicly verifiable on-chain registry.

## Technical Requirements

- **Runtime Environment:** Python 3.12.3+
- **Backend Framework:** Flask, Flask-SQLAlchemy (ORM)
- **Database:** PostgreSQL (hosted via Supabase with Session Pooling on port 6543)
- **Database Driver:** psycopg2-binary
- **Cloud Storage:** Cloudinary (for property image uploads)
- **Web3 Integration:** MetaMask Browser Extension, Ethers.js
- **Smart Contracts:** Solidity (^0.8.x), Ethereum Sepolia Testnet
- **Deployment Hosting:** Vercel (Serverless Python Runtime)

## Repository Structure

```text
rrebp/
├── app.py                   # Main Flask application and server entry point
├── models.py                # SQLAlchemy database schema and models (Broker, Property, etc.)
├── seed.py / seed_admin.py  # Database initialization and secure Super Admin injection scripts
├── vercel.json              # Vercel serverless deployment configuration
├── requirements.txt         # Python dependencies and libraries
├── .env.example             # Template for required environment variables
├── routes/                  # Flask Blueprints for modular routing
│   ├── landing.py           # Public-facing properties, verification, and authentication
│   ├── association.py       # Association Admin dashboard and review logic
│   └── broker.py            # Broker dashboard, property listing, and settings
├── templates/               # Jinja2 HTML templates
│   ├── base.html            # Public layout wrapper
│   ├── assoc_base.html      # Association Admin layout wrapper
│   ├── broker_base.html     # Broker portal layout wrapper
│   └── ...                  # Individual view templates
├── static/                  # Static assets
│   ├── css/                 # Custom stylesheets
│   └── data/                # JSON datasets (e.g., locations.json for Rwanda provinces)
└── contracts/               # Web3 Smart Contract source files
    └── RREBP_BrokerRegistry.sol
```

## Smart Contract Snippets

RREBP uses a Solidity smart contract, `RREBP_BrokerRegistry.sol`, to maintain an on-chain registry of brokers. The contract utilizes a hash generated from the broker's information, the crypto wallet address of the real estate association, a boolean indicating whether the broker is active, and a registration timestamp.

Here is a snippet:

```solidity
struct Broker {
    bytes32 brokerHash;
    address associationWallet;
    bool isActive;
    uint256 registeredAt;
}

mapping(bytes32 => Broker) public brokers;
mapping(address => bool) public authorizedAssociations;
```

## Data Visualization

Data in the RREBP platform is visualized using role-specific administrative dashboards and a public verification page.

- **Super Admin Dashboard:** Displays metrics on active organizations, registered admins, and suspended entities.
- **Association Admin Dashboard:** Displays aggregated data on total brokers and those currently verified on-chain.
- **Public Verification Page:** Allows end-users to check a broker's registration hash directly against the deployed smart contract.

## Security Measures

The RREBP platform combines robust off-chain security with blockchain immutability.

- **Password Hashing:** Passwords are mathematically hashed before being stored in the database using the Werkzeug security library.
- **Role-Based Access Control (RBAC):** Strict view and action permissions are separated between Super Admins, Association Admins, and Brokers using Python decorators.
- **Data Privacy:** Personally Identifiable Information (PII) is kept securely off-chain in the PostgreSQL database, while cryptographic hashes are utilized for blockchain verification.
- **Wallet Authorization:** Only pre-approved association wallets can perform authorized write operations to the blockchain.
- **Duplicate Prevention:** The smart contract logic explicitly rejects duplicate broker registrations.

## Schematic Design and Component Interaction

```text
    Super Admin / Association Admin
                |
         Frontend Interface
        (HTML, CSS, JavaScript)
                |
          ______|______
         |             |
         |             |
    Flask Backend   MetaMask
         |             |
         |             |
  Supabase Database  Ethers.js
    (PostgreSQL)       |
         |             |
Posting Properties Ethereum Smart
         |           Contract
Rating properties      |
                       |
                Broker Verification
                       |
                  Public Users
```

### Main Components

- **Frontend (HTML, CSS, JavaScript):** Provides the landing, administrative, and public verification interfaces.
- **Backend (Flask):** Serves the application logic, handles authentication, organization/association management, and brokers' property media routing.
- **Database (Supabase PostgreSQL):** Provides scalable cloud storage for off-chain relational data, including users, properties, and reviews.
- **Cloud Storage (Cloudinary):** Handles direct uploads and global CDN delivery for property gallery images.
- **MetaMask and Ethers.js:** Facilitates secure smart contract and wallet interactions from the browser.
- **Smart Contract (RREBP_BrokerRegistry):** Acts as the decentralized, tamper-proof verification registry.

### Diagram Description

The Super Admin and Association Admin interact with the frontend interface, built using HTML, CSS, and JavaScript. The frontend communicates with the Flask backend, which handles application logic and reads and writes data to the cloud-hosted Supabase PostgreSQL database.

Specific administrative actions trigger MetaMask through the Ethers.js library to execute transactions on the deployed Ethereum smart contract. End users can then utilize the public verification interface to cryptographically verify a broker's registration status on-chain.

## How to Setup the Environment

### 1. Clone the Repository

```bash
git clone https://github.com/desparvis/rrebp.git
cd rrebp
```

### 2. Create and Activate a Virtual Environment

```bash
python -m venv .venv
```

```bash
# On Linux/macOS
source .venv/bin/activate

# On Windows
.venv\Scripts\activate
```

### 3. Install Backend Dependencies

```bash
pip install -r requirements.txt
```

### 4. Create Your Environment Variables

Create a `.env` file in the root directory and configure the required environment variables:

```env
SECRET_KEY=your_secure_random_key

SUPERADMIN_EMAIL=credo@rrebp.rw
SUPERADMIN_PASSWORD=your_secure_password

DATABASE_URL=postgresql+psycopg2://[user]:[URL-encoded-password]@[supabase-pooler-url]:6543/postgres

CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_api_key
CLOUDINARY_API_SECRET=your_api_secret
```

**Note:** Replace the placeholder values with your actual credentials. Never commit your `.env` file or expose your secret keys in the repository.

### 5. Initialize the Database and Seed Admin

Run the following command to create the PostgreSQL tables in Supabase and inject the Super Admin account:

```bash
python seed_admin.py
```

### 6. Run the Flask Application

```bash
python app.py
```

The Flask application should now be running in your local development environment.

## Deployment Architecture

The application architecture has successfully transitioned from a local development environment to a scalable, cloud-based infrastructure.

**Web Application Hosting (Vercel):** The Flask backend and frontend templates are deployed serverless via Vercel using the `vercel.json` configuration. Vercel provides continuous integration from GitHub, fast global delivery, and out-of-the-box HTTPS for secure web traffic.

**Database Migration (Supabase):** The database relies on Supabase, a managed PostgreSQL database. Connected via an IPv4 Session Pooler (port 6543), Supabase provides the scalability, concurrency, and cloud accessibility required for a production-level real estate registry.

**Smart Contract Deployment (Ethereum Sepolia Testnet):** The `RREBP_BrokerRegistry` smart contract is deployed to the Sepolia testnet. Sepolia mirrors the Ethereum Mainnet environment, allowing full interaction with MetaMask and Ethers.js using test ETH. This provides a functional environment for demonstration and verification without requiring real financial transactions or mainnet gas fees.

## Author

**Credo Desparvis Gutabarwa**
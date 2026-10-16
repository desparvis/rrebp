# Rwanda Real Estate Brokers Platform(RREBP)

Github Repository: [link](https://github.com/desparvis/rrebp) <br>
MVP Demo Video: [youtubelink](https://youtu.be/1rWhGEpu08I?si=vz7Anm2vfKNwKzqC)

## Description

Rwanda Real Estate Brokers Platform is a web2 and web3 application designed to improve transparency in the Rwandan real estate sector. It has normal web2 features such as authentication, creation, editing, deleting features. These features allow users to register real estate associations, approve the associations, and register brokers locally. This platform also has web3 capabilities as brokers can be recorded on the blockchain to maintain on-chain registry for brokers.

## Smart Contract Snippets

RREBP uses a Solidity Smart Contract, the RREBP_BrokerRegistry.sol to maintain on-chain registry of brokers. The contract uses a hash that uses the broker's information, the address that stores the crypto wallet of the real estate association, a boolean for showing if the broker is active, and the registration timestamp.

Here is a snippet:
```
struct Broker {
    bytes32 brokerHash;
    address associationWallet;
    bool isActive;
    uint256 registeredAt;
}

mapping(bytes32 => Broker) public brokers;<br>
mapping(address => bool) public authorizedAssociations;
```

## Data visualization

Data in the RREBP platform is visualized using admin dashboards and a public verification page.<br>
- On the superadmin dashboard, data about active organizations, registered admins, suspended entinties can also be shown through numbers.<br>
- On the assocation admins dashboard, data about total brokers and those that verified on chain can be showed through numbers.<br>
- On the verification page, the broker registration is checked against the smart contract

## Security measures

The RREBP platform combines both off-chain security and blockchain verification.<br>
- Password hashing: Passwords are hashed before being stored on the database using Werkzeug security tools.<br>
- Role-Based Access: Separate permissions are given to different admins, the super admin has most control while the association admin controls the brokers.<br>
- Data Privacy: Broker identification information is kept off-chain while cryptographic hashes are used for blockchain verification.<br>
- Wallet Authorization: Only approved association wallets can perform authorized blockchain operations.
- Duplicate Prevention: The smart contract rejects duplicate broker registrations.

## Schematic Design and Component Interaction

    Super Admin / Association Admin
              |
       Frontend Interface
      (HTML, CSS, JavaScript)
              |
        ______|______
       |             |
       |             |
 Flask Backend    MetaMask
       |             |
       |             |
 SQLite Database  Ethers.js
                     |
              Ethereum Smart
                  Contract
                     |
              Broker Verification
                     |
               Public Users
### Main components
### Diagram description

Here we can see that the Super Admin and the Association Admin use the frontend interface which is built using JavaScript, HTML, and CSS. It talks to a Flask backend which stores the data on a SQLite Database. In addition, when interacting with the interface, actions that trigger metamask to perform a transaction. That is because of the ethers.js library helps interact with the deployed smart contract. End users can then use the public verification to interface to verify a broker's status and information.


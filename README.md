# Rwanda Real Estate Brokers Platform(RREBP)

Github Repository: [link](https://github.com/desparvis/rrebp) <br>
MVP Demo Video: [youtubelink](https://youtu.be/1rWhGEpu08I?si=vz7Anm2vfKNwKzqC)

## Description

Rwanda Real Estate Brokers Platform is a web2 and web3 application designed to improve transparency in the Rwandan real estate sector. It has normal web2 features such as authentication, creation, editing, deleting features. These features allow users to register real estate associations, approve the associations, and register brokers locally. This platform also has web3 capabilities as brokers can be recorded on the blockchain to maintain on-chain registry for brokers.

## Smart Contract Snippets

RREBP uses a Solidity Smart Contract, the RREBP_BrokerRegistry.sol to maintain on-chain registry of brokers. The contract uses a hash that uses the broker's information, the address that stores the crypto wallet of the real estate association, a boolean for showing if the broker is active, and the registration timestamp.

Here is a snippet:

struct Broker {
    bytes32 brokerHash;
    address associationWallet;
    bool isActive;
    uint256 registeredAt;
}

mapping(bytes32 => Broker) public brokers;
mapping(address => bool) public authorizedAssociations;

## Data visualization

Data in the RREBP platform is visualized using admin dashboards and a public verification page.
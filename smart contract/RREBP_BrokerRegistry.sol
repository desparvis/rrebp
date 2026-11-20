// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract RREBP_BrokerRegistry {
    
    struct Broker {
        bytes32 brokerHash;       // Hash of broker's identity
        address associationWallet;// Association wallet address
        bool isActive;            // Cheap status toggle
        uint256 registeredAt;     // Timestamp for registration
    }

    address public owner; // The Super Admin who deploys the contract

    // Mapping a unique license hash to the Broker struct
    mapping(bytes32 => Broker) public brokers;
    
    // Giving access to authorized admins only for registering brokers
    mapping(address => bool) public authorizedAssociations;

    event BrokerRegistered(bytes32 indexed brokerHash, address association);
    event BrokerStatusUpdated(bytes32 indexed brokerHash, bool isActive);

    // Set the deployer as the owner
    constructor() {
        owner = msg.sender;
    }

    modifier onlyAuthorized() {
        require(authorizedAssociations[msg.sender], "Not an authorized association");
        _;
    }

    // NEW: Restrict actions to the Super Admin
    modifier onlyOwner() {
        require(msg.sender == owner, "Only the Super Admin can perform this action");
        _;
    }

    // Registering new broker using their hash
    function registerBroker(bytes32 _brokerHash) public onlyAuthorized {
        require(brokers[_brokerHash].registeredAt == 0, "Broker already registered");

        brokers[_brokerHash] = Broker({
            brokerHash: _brokerHash,
            associationWallet: msg.sender,
            isActive: true,
            registeredAt: block.timestamp
        });

        emit BrokerRegistered(_brokerHash, msg.sender);
    }

    // Adding an association admin wallet
    function addAssociation(address _adminWallet) public onlyOwner {
        authorizedAssociations[_adminWallet] = true;
    }

    // Suspending broker and activating them
    function toggleBrokerStatus(bytes32 _brokerHash, bool _status) public onlyAuthorized {
        require(brokers[_brokerHash].registeredAt != 0, "Broker does not exist");
        require(brokers[_brokerHash].associationWallet == msg.sender, "Not your broker");
        
        brokers[_brokerHash].isActive = _status;
        emit BrokerStatusUpdated(_brokerHash, _status);
    }
}
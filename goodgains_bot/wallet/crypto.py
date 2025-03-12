from web3 import Web3
from eth_account.account import Account
from eth_utils import is_checksum_address
import logging
from config import INFURA_URL, fernet, ENCRYPTED_WALLET_PRIVATE_KEY, CONTRACT_ADDRESS

logger = logging.getLogger('goodgains_bot')


def get_web3_instance():
    """Get a Web3 instance connected to the provider."""
    return Web3(Web3.HTTPProvider(INFURA_URL))


def get_web3_account():
    """Securely decrypt and return the web3 account."""
    if not fernet or not ENCRYPTED_WALLET_PRIVATE_KEY:
        logger.error("Missing encryption key or private key")
        return None

    try:
        decrypted_key = fernet.decrypt(ENCRYPTED_WALLET_PRIVATE_KEY.encode()).decode()
        account = Account.from_key(decrypted_key)
        return account
    except Exception as e:
        logger.error(f"Error decrypting private key: {e}")
        return None


def load_contract():
    """Load the betting smart contract."""
    try:
        web3 = get_web3_instance()

        # Load contract ABI
        with open('contract_abi.json', 'r') as f:
            contract_abi = json.load(f)

        # Create contract instance
        contract = web3.eth.contract(
            address=Web3.to_checksum_address(CONTRACT_ADDRESS),
            abi=contract_abi
        )

        return contract
    except Exception as e:
        logger.error(f"Error loading contract: {e}")
        return None


def validate_eth_address(address):
    """Validate an Ethereum address format."""
    if not address:
        return False

    # Check basic format
    if not address.startswith('0x') or len(address) != 42:
        return False

    # Check checksum
    try:
        return is_checksum_address(address)
    except:
        return False
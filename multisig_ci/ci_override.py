import os
from copy import copy
from brownie_safe import BrownieSafeBase, BrownieSafe
from brownie_safe import ExecutionFailure, PATCHED_SAFE_VERSIONS
from brownie import accounts, network, chain, Contract
from gnosis.safe.safe_tx import SafeTx
from gnosis.safe.safe import SafeV111, SafeV120, SafeV130, SafeV141
from gnosis.eth.ethereum_client import EthereumNetwork
from eth_abi import encode
from eth_utils import keccak
from typing import Optional, Union
from brownie.network.account import LocalAccount, Account
from brownie.network.contract import _explorer_tokens
from brownie._config import CONFIG
from _pytest.monkeypatch import MonkeyPatch
from brownie.network.rpc import anvil 
from multisig_ci.sentry_wrapper import custom_sentry_trace


@custom_sentry_trace
def mine_override(timestamp: Optional[int] = None) -> None:
    if timestamp:
        anvil._request("evm_setNextBlockTimestamp", [timestamp])
    anvil._request("evm_mine", [])

monkeypatch = MonkeyPatch()
monkeypatch.setattr(anvil, 'mine', mine_override)

# CI horribleness lurks below
# If running in CI, let's override BrownieSafeBase.post_transaction so
# that it writes a file with the nonce. This is used to later tag
# the pull request with a label matching the nonce

DELEGATE_ADDRESS = os.environ.get("DELEGATE_ADDRESS")
home_directory = os.environ.get("HOME")
BASE_CHAIN_ID = 8453
OPTIMISM_CHAIN_ID = 10
FANTOM_CHAIN_ID = 250
BERACHAIN_CHAIN_ID = 80094
KATANA_CHAIN_ID = 747474
ALT_DEFAULT_MULTISEND = "0xA1dabEF33b3B82c7814B6D82A79e50F4AC44102B"

gnosis_frontend_urls = {
    1: 'https://app.safe.global/transactions/queue?safe=eth:{0}',
    4: 'https://app.safe.global/transactions/queue?safe=rin:{0}',
    5: 'https://app.safe.global/transactions/queue?safe=gor:{0}',
    10: 'https://app.safe.global/transactions/queue?safe=oeth:{0}',
    56: 'https://app.safe.global/transactions/queue?safe=bnb:{0}',
    100: 'https://app.safe.global/transactions/queue?safe=xdai:{0}',
    137: 'https://app.safe.global/transactions/queue?safe=matic:{0}',
    250: 'https://safe.fantom.network/transactions/queue?safe=ftm:{0}',
    8453: 'https://app.safe.global/transactions/queue?safe=base:{0}',
    146: 'https://app.safe.global/transactions/queue?safe=sonic:{0}',
    42161: 'https://app.safe.global/transactions/queue?safe=arb1:{0}',
    80094: 'https://app.safe.global/transactions/queue?safe=berachain:{0}',
    747474: 'https://app.safe.global/transactions/queue?safe=katana:{0}',
}

_explorer_tokens['basescan'] = 'BASESCAN_TOKEN'

class DelegateSafeBase(BrownieSafeBase):
    @custom_sentry_trace
    def __init__(self, address, ethereum_client):
        if CONFIG.network_type != "development":
            acct = Account(address)
            if acct not in accounts._accounts:
                accounts._accounts.append(acct)

        super().__init__(address, ethereum_client)

    @property
    def is_ci(self):
        return os.environ.get("CI", "").lower() == "true"

    @property
    def is_send(self):
        return os.environ.get("GITHUB_ACTION_SEND", "").lower() == "true"

    @custom_sentry_trace
    def post_transaction(self, safe_tx: SafeTx):
        super().post_transaction(safe_tx)

        if self.is_ci and self.is_send:
            if "{1}" in self.frontend_url:
                formatted_frontend_url = self.frontend_url.format(self.address, safe_tx.safe_tx_hash.hex())
            else:
                formatted_frontend_url = self.frontend_url.format(self.address)

            with open(os.getenv('GITHUB_ENV'), 'a') as f:
                f.write("SAFE_LINK={0}\n".format(formatted_frontend_url))
            with open(os.path.join(home_directory, "safe.txt"), "w") as f:
                f.write(str(formatted_frontend_url))
            with open(os.getenv('GITHUB_ENV'), 'a') as f:
                f.write("NONCE={0}\n".format(str(safe_tx.safe_nonce)))
            with open(os.path.join(home_directory, "nonce.txt"), "w") as f:
                f.write(str(safe_tx.safe_nonce))
            exit(0)

    @custom_sentry_trace
    def preview_tx(self, safe_tx: SafeTx, events=True, call_trace=False):
        if self.is_ci:
            events = False
            call_trace = False

        tx = copy(safe_tx)
        safe = Contract.from_abi('Gnosis Safe', self.address, self.contract.abi)
        # Replace pending nonce with the subsequent nonce, this could change the safe_tx_hash
        tx.safe_nonce = safe.nonce()
        # Forge signatures from the needed amount of owners, skip the one which submits the tx
        # Owners must be sorted numerically, sorting as checksum addresses may yield wrong order
        threshold = safe.getThreshold()
        sorted_owners = sorted(safe.getOwners(), key=lambda x: int(x, 16))
        owners = [accounts.at(owner, force=True) for owner in sorted_owners[:threshold]]
        # Signautres are encoded as [bytes32 r, bytes32 s, bytes8 v]
        # Pre-validated signatures are encoded as r=owner, s unused and v=1.
        # https://docs.gnosis.io/safe/docs/contracts_signatures/#pre-validated-signatures
        tx.signatures = b''.join([encode(['address', 'uint'], [str(owner), 0]) + b'\x01' for owner in owners])

        # approvedHashes are in slot 8 and have type of mapping(address => mapping(bytes32 => uint256))
        for owner in owners[:threshold]:
            outer_key = keccak(encode(['address', 'uint'], [str(owner), 8]))
            slot = int.from_bytes(keccak(tx.safe_tx_hash + outer_key), 'big')
            self.set_storage(tx.safe_address, slot, 1)

        payload = tx.w3_tx.build_transaction({'gas': str(chain.block_gas_limit), 'maxFeePerGas': 100})
        receipt = owners[0].transfer(payload['to'], payload['value'], gas_limit=payload['gas'], data=payload['data'])

        if 'ExecutionSuccess' not in receipt.events:
            receipt.info()
            receipt.call_trace(True)
            raise ExecutionFailure()

        if events:
            receipt.info()
        if call_trace:
            receipt.call_trace(True)
        return receipt

    @custom_sentry_trace
    def get_signer(self, signer: Optional[Union[LocalAccount, str]] = None) -> LocalAccount:
        if not self.is_ci:
            return super().get_signer(signer)

        if self.is_send:
            key = os.environ.get("PRIVATE_KEY")
            assert (
                key is not None
            ), "CI environment missing PRIVATE_KEY environment variable. Please add it as a repository secret."
            user = accounts.add(key)
            assert (
                user.address == DELEGATE_ADDRESS
            ), "Delegate address mismatch. Check you have correct private key."
            return user
        
        return None

    @custom_sentry_trace
    def sign_transaction(self, safe_tx: SafeTx, signer=None) -> SafeTx:
        if not self.is_ci:
            return super().sign_transaction(safe_tx, signer)

        if not self.is_send:
            print("CI dry-run enabled, set send to true to run to completion")
            exit(0)
        
        return super().sign_transaction(safe_tx, signer)

class DelegateSafeV111(DelegateSafeBase, SafeV111):
    pass

class DelegateSafeV120(DelegateSafeBase, SafeV120):
    pass

class DelegateSafeV130(DelegateSafeBase, SafeV130):
    pass

class DelegateSafeV141(DelegateSafeBase, SafeV141):
    pass

PATCHED_SAFE_VERSIONS['1.1.1'] = DelegateSafeV111
PATCHED_SAFE_VERSIONS['1.2.0'] = DelegateSafeV120
PATCHED_SAFE_VERSIONS['1.3.0'] = DelegateSafeV130
PATCHED_SAFE_VERSIONS['1.4.1'] = DelegateSafeV141

def DelegateSafe(address, base_url=None, multisend=None):
    """
    Create an BrownieSafeBase from an address or a ENS name and use a default connection.
    """
    if network.chain.id in gnosis_frontend_urls:
        frontend_url = gnosis_frontend_urls[network.chain.id]
    else:
        frontend_url = gnosis_frontend_urls[1]

    if not base_url:
        if network.chain.id == FANTOM_CHAIN_ID:
            base_url = "https://safe-txservice.fantom.network"
        elif network.chain.id == BERACHAIN_CHAIN_ID:
            base_url = "https://safe-transaction-berachain.safe.global"
        elif network.chain.id == KATANA_CHAIN_ID:
            base_url = "https://safe-transaction-katana.safe.global"

    if not multisend and (network.chain.id == OPTIMISM_CHAIN_ID or network.chain.id == BASE_CHAIN_ID):
        multisend = ALT_DEFAULT_MULTISEND

    safe = BrownieSafe(address, base_url, multisend)
    safe.frontend_url = frontend_url
    return safe


if os.environ.get("CI", "").lower() == "true":
    with open(os.path.join(home_directory, "alive.signal"), "w") as f:
        f.write("I am alive")

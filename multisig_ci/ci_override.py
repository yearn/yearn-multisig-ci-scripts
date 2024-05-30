import os
from copy import copy
from brownie_safe import BrownieSafe as ApeSafe
from brownie_safe import ExecutionFailure
from brownie import accounts, network, chain, Contract
from gnosis.safe.safe_tx import SafeTx
from eth_abi import encode
from eth_utils import keccak
from typing import Optional, Union
from brownie.network.account import LocalAccount
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

from brownie_safe import CUSTOM_MULTISENDS

for e, v in CUSTOM_MULTISENDS.copy().items():
    CUSTOM_MULTISENDS[e.value] = v

# CI horribleness lurks below
# If running in CI, let's override ApeSafe.post_transaction so
# that it writes a file with the nonce. This is used to later tag
# the pull request with a label matching the nonce

DELEGATE_ADDRESS = os.environ.get("DELEGATE_ADDRESS")
home_directory = os.environ.get("HOME")
BASE_CHAIN_ID = 8453

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
    42161: 'https://app.safe.global/transactions/queue?safe=arb1:{0}',
}

_explorer_tokens['basescan'] = 'BASESCAN_TOKEN'

class DelegateSafe(ApeSafe):
    @custom_sentry_trace
    def __init__(self, address, base_url=None, multisend=None):
        """
        Create an ApeSafe from an address or a ENS name and use a default connection.
        """
        if network.chain.id in gnosis_frontend_urls:
            self.frontend_url = gnosis_frontend_urls[network.chain.id]
        else:
            self.frontend_url = gnosis_frontend_urls[1]
        
        if not base_url and network.chain.id == BASE_CHAIN_ID:
            base_url = "https://safe-transaction-base.safe.global"

        super().__init__(address, base_url=base_url, multisend=multisend)

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

        payload = tx.w3_tx.build_transaction()
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

if os.environ.get("CI", "").lower() == "true":
    with open(os.path.join(home_directory, "alive.signal"), "w") as f:
        f.write("I am alive")

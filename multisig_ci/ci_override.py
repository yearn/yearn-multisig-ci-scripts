import os
from copy import copy
from ape_safe import ApeSafe, transaction_service, multisends
from brownie import accounts, network, chain, Contract
from gnosis.safe.safe_tx import SafeTx
from eth_abi import encode_abi
from typing import Optional, Union
from brownie.network.account import LocalAccount
from brownie._config import CONFIG

# CI horribleness lurks below
# If running in CI, let's override ApeSafe.post_transaction so
# that it writes a file with the nonce. This is used to later tag
# the pull request with a label matching the nonce

DELEGATE_ADDRESS = os.environ.get("DELEGATE_ADDRESS")
home_directory = os.environ.get("HOME")

gnosis_frontend_urls = {
    'gnosis': {
        1: 'https://app.safe.global/eth:{0}/transactions/queue',
        4: 'https://app.safe.global/rin:{0}/transactions/queue',
        5: 'https://app.safe.global/gor:{0}/transactions/queue',
        10: 'https://app.safe.global/oeth:{0}/transactions/queue',
        56: 'https://app.safe.global/bsc:{0}/transactions/queue',
        100: 'https://app.safe.global/xdai:{0}/transactions/queue',
        137: 'https://app.safe.global/matic:{0}/transactions/queue',
        250: 'https://safe.fantom.network/ftm:{0}/transactions/queue',
        42161: 'https:/app.safe.global/arb1:{0}/transactions/queue'
    },
    'yearn': {
        1: 'http://mainnet.gnosis.yearn.tools/eth:{0}/transactions/queue',
        4: 'http://mainnet.gnosis.yearn.tools/rin:{0}/transactions/queue',
        56: 'http://mainnet.gnosis.yearn.tools/bsc:{0}/transactions/queue',
        100: 'http://mainnet.gnosis.yearn.tools/xdai:{0}/transactions/queue',
        137: 'http://mainnet.gnosis.yearn.tools/matic:{0}/transactions/queue',
        42161: 'http://mainnet.gnosis.yearn.tools/arb1:{0}/transactions/queue'
    }
}


class DelegateSafe(ApeSafe):
    def __init__(self, address, base_url=None, multisend=None):
        """
        Create an ApeSafe from an address or a ENS name and use a default connection.
        """
        
        transaction_service[250] = "https://safe-txservice.fantom.network"
        transaction_service[10] = "https://safe-transaction.optimism.gnosis.io"
        multisends[10] = "0x998739BFdAAdde7C933B942a68053933098f9EDa"
        backend_urls = {
            'gnosis': transaction_service,
            'yearn': {1: 'https://safe-transaction.mainnet.gnosis.yearn.tools/'}
        }

        # default to gnosis if we don't have a yearn version
        if network.chain.id in backend_urls["gnosis"]:
            if network.chain.id not in backend_urls[self.backend_type]:
                backend_url_from_config = backend_urls["gnosis"][network.chain.id]
                self.frontend_url = ["gnosis"][network.chain.id]
            else:
                backend_url_from_config = backend_urls[self.backend_type][network.chain.id]
                self.frontend_url = gnosis_frontend_urls[self.backend_type][network.chain.id]
        else:
            backend_url_from_config = backend_urls["gnosis"][1]
            self.frontend_url = gnosis_frontend_urls["gnosis"][1]

        self.base_url = base_url or backend_url_from_config
        super().__init__(address, base_url=self.base_url, multisend=multisend)

    @property
    def is_ci(self):
        return os.environ.get("CI", "").lower() == "true"

    @property
    def is_send(self):
        return os.environ.get("GITHUB_ACTION_SEND", "").lower() == "true"

    @property
    def backend_type(self):
        backend_from_env = os.environ.get("BE", "").lower()
        return backend_from_env if backend_from_env != "" else "gnosis"

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

    def preview(self, safe_tx: SafeTx, events=True, call_trace=False, reset=True):
        if self.is_ci:
            events = False
            call_trace = False

        """
        Dry run a Safe transaction in a forked network environment.
        """
        if reset:
            chain.reset()

        tx = copy(safe_tx)
        safe = Contract.from_abi('Gnosis Safe', self.address, self.get_contract().abi)
        # Replace pending nonce with the subsequent nonce, this could change the safe_tx_hash
        tx.safe_nonce = safe.nonce()
        # Forge signatures from the needed amount of owners, skip the one which submits the tx
        # Owners must be sorted numerically, sorting as checksum addresses may yield wrong order
        threshold = safe.getThreshold()
        sorted_owners = sorted(safe.getOwners(), key=lambda x: int(x, 16))
        owners = [accounts.at(owner, force=True) for owner in sorted_owners[:threshold]]
        for owner in owners:
            safe.approveHash(tx.safe_tx_hash, {'from': owner})

        # Signautres are encoded as [bytes32 r, bytes32 s, bytes8 v]
        # Pre-validated signatures are encoded as r=owner, s unused and v=1.
        # https://docs.gnosis.io/safe/docs/contracts_signatures/#pre-validated-signatures
        tx.signatures = b''.join([encode_abi(['address', 'uint'], [str(owner), 0]) + b'\x01' for owner in owners])
        payload = tx.w3_tx.buildTransaction({'gas': str(chain.block_gas_limit)})
        receipt = owners[0].transfer(payload['to'], payload['value'], gas_limit=payload['gas'], data=payload['data'])

        if 'ExecutionSuccess' not in receipt.events:
            receipt.info()
            receipt.call_trace(True)
            raise ApeSafe.ExecutionFailure()
        if events:
            receipt.info()
        if call_trace:
            receipt.call_trace(True)
        return receipt


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

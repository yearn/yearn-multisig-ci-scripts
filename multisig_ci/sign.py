from multisig_ci.safes import safe

def _tenderly_fork(safe):
   import requests
   import brownie
   from brownie import chain

   fork_base_url = "https://simulate.yearn.network/fork"
   payload = {"network_id": str(chain.id)}
   resp = requests.post(fork_base_url, headers={}, json=payload)
   fork_id = resp.json()["simulation_fork"]["id"]
   fork_rpc_url = f"https://rpc.tenderly.co/fork/{fork_id}"
   print(fork_rpc_url)
   tenderly_provider = brownie.web3.HTTPProvider(fork_rpc_url, {"timeout": 600})
   brownie.web3.provider = tenderly_provider
   safe.w3.provider = tenderly_provider
   print(f"https://dashboard.tenderly.co/yearn/yearn-web/fork/{fork_id}")

def sign(nonce_arg = None, skip_preview = False, post_tx = False, tenderly_fork = False):
    def _sign(func):
        def wrapper():
            if tenderly_fork:
                _tenderly_fork(safe)
            func()
            safe_tx = safe.multisend_from_receipts(safe_nonce=nonce)
            if not skip_preview:
                safe.preview(safe_tx, call_trace=False)

            if not post_tx and not safe.is_ci:
                print("dry-run finished, run again with @sign(post_tx = True) to sign and submit the tx.")
            else:
                safe.sign_transaction(safe_tx)
                safe.post_transaction(safe_tx)

        return wrapper

    if callable(nonce_arg):
        nonce = None
        return _sign(nonce_arg)

    nonce = int(nonce_arg) if nonce_arg else nonce_arg
    return _sign

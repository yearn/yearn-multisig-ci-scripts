from multisig_ci.safes import safe
from multisig_ci.sentry_wrapper import custom_sentry_trace, CustomSentryTransaction, CustomSentrySpan

@custom_sentry_trace
def _tenderly_fork(safe, timeout_seconds):
   import requests
   import brownie
   from brownie import chain

   fork_rpc_url_provider = "https://fork.ysim.xyz/create"
   payload = {"chain_id": str(chain.id)}
   resp = requests.post(fork_rpc_url_provider, headers={}, json=payload).json()
   fork_id = resp["vnet_id"]
   fork_rpc_url = resp["rpc_url"]
   print(fork_rpc_url)
   tenderly_provider = brownie.web3.HTTPProvider(fork_rpc_url, {"timeout": timeout_seconds})
   brownie.web3.provider = tenderly_provider
   safe.w3.provider = tenderly_provider
   print(f"https://dashboard.tenderly.co/yearn/robowoofy/testnet/{fork_id}")

@custom_sentry_trace
def sign(nonce_arg = None, skip_preview = False, post_tx = False, tenderly_fork = False, tenderly_timeout_seconds = 60):
    global SENTRY_IMPORTED
    def _sign(func):
        def wrapper():
            if safe.is_ci and safe.is_send:
                op = "ci_send"
            else:
                op = "ci_dry_run"

            with CustomSentryTransaction(op=op, name=func.__name__):
                if tenderly_fork:
                    with CustomSentrySpan(description="tenderly_fork"):
                        _tenderly_fork(safe, tenderly_timeout_seconds)

                with CustomSentrySpan(description="run_func"):
                    func()
                
                with CustomSentrySpan(description="build_tx"):
                    safe_tx = safe.multisend_from_receipts(safe_nonce=nonce)

                if not skip_preview:
                    with CustomSentrySpan(description="preview_tx"):
                        safe.preview(safe_tx, call_trace=False)

                if not post_tx and not safe.is_ci:
                    print("dry-run finished, run again with @sign(post_tx = True) to sign and submit the tx.")
                else:
                    if safe.is_ci and not safe.is_send:
                        print("CI dry-run enabled, set send to true to run to completion")
                        return

                    with CustomSentrySpan(description="sign_tx"):
                        safe.sign_transaction(safe_tx)
                    with CustomSentrySpan(description="post_tx"):
                        safe.post_transaction(safe_tx)

        return wrapper

    if callable(nonce_arg):
        nonce = None
        return _sign(nonce_arg)

    nonce = int(nonce_arg) if nonce_arg else nonce_arg
    return _sign

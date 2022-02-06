from multisig_ci.run_brownie import run_brownie
from multisig_ci.hydrate_ci_cache import hydrate_compiler_cache
import sys

if __name__ == '__main__':
    if 'hydrate_compiler_cache' in sys.argv:
        hydrate_compiler_cache()
        sys.exit(0)

    run_brownie(sys.argv[1:])
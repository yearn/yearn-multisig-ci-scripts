from multisig_ci.run_brownie import run_brownie
import sys

if __name__ == '__main__':
    run_brownie(sys.argv[1:])
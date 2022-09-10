import os
from multisig_ci.ci_override import DelegateSafe as ApeSafe
from brownie import network

address = None
if network.chain.id == 250:
    address = os.getenv("FTM_SAFE_ADDRESS")
elif network.chain.id == 137:
    address = os.getenv("POLYGON_SAFE_ADDRESS")
elif network.chain.id == 56:
    address = os.getenv("BSC_SAFE_ADDRESS")
elif network.chain.id == 4:
    address = os.getenv("RIN_SAFE_ADDRESS")
elif network.chain.id == 42161:
    address = os.getenv("ARB_SAFE_ADDRESS")
elif network.chain.id == 100:
    address = os.getenv("GNOSIS_SAFE_ADDRESS")
elif network.chain.id == 10:
    address = os.getenv("OPTI_SAFE_ADDRESS")
elif network.chain.id == 5:
    address = os.getenv("GOR_SAFE_ADDRESS")
else:
    address = os.getenv("ETH_SAFE_ADDRESS")

safe = None
if address:
    safe = ApeSafe(address)

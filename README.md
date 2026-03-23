Tools for multisig CI


dev
```
export PATH=$PATH:$HOME/.poetry/bin
poetry build
poetry publish -r testpypi
pip3 install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple  multisig-ci==0.0.8
```

prod
```
export PATH=$PATH:$HOME/.poetry/bin
poetry build
poetry publish
```

safe transaction service auth
```
export SAFE_AUTH_TOKEN=your_safe_api_token
```

`SAFE_TRANSACTION_SERVICE_API_KEY` is also supported for compatibility with Safe's API key naming.

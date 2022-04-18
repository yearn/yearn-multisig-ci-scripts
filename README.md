Tools for multisig CI

dev
```
export PATH=$PATH:$HOME/.poetry/bin
poetry build
poetry publish -r testpypi
pip3 install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple  multisig-ci==0.0.5b2
```

prod
```
export PATH=$PATH:$HOME/.poetry/bin

poetry build
poetry publish
```
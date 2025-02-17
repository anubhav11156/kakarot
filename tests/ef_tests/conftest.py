import json
import logging
import os
from pathlib import Path

import pytest
import pytest_asyncio
from starkware.starknet.core.os.contract_address.contract_address import (
    calculate_contract_address_from_hash,
)
from starkware.starknet.testing.contract import DeclaredClass, StarknetContract
from starkware.starknet.testing.starknet import Starknet

# Root of the GeneralStateTest in BlockchainTest format
EF_GENERAL_STATE_TEST_ROOT_PATH = Path(
    "./tests/ef_tests/test_data/BlockchainTests/GeneralStateTests/"
)


DEFAULT_NETWORK = "Shanghai"

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def pytest_generate_tests(metafunc):
    """
    Parametrizes `ef_blockchain_test` fixture with cases loaded from the
    Ethereum Foundation tests repository, see:
    https://github.com/kkrt-labs/kakarot/blob/main/.gitmodules#L7.
    """
    if (
        "ef_blockchain_test" not in metafunc.fixturenames
        or os.getenv("EF_TESTS") is None
    ):
        return

    if not EF_GENERAL_STATE_TEST_ROOT_PATH.exists():
        logger.warning(
            "EFTests directory %s doesn't exist. Run `make setup`",
            str(EF_GENERAL_STATE_TEST_ROOT_PATH),
        )
        metafunc.parametrize("ef_blockchain_test", [])
        return

    test_ids, test_cases = zip(
        *[
            (name, content)
            for (root, _, files) in os.walk(EF_GENERAL_STATE_TEST_ROOT_PATH)
            for file in files
            if file.endswith(".json")
            for name, content in json.loads((Path(root) / file).read_text()).items()
            if content["network"] == DEFAULT_NETWORK
        ]
    )

    metafunc.parametrize(
        "ef_blockchain_test",
        test_cases,
        ids=test_ids,
    )


@pytest_asyncio.fixture(scope="session")
async def kakarot(
    starknet: Starknet,
    eth: StarknetContract,
    contract_account_class: DeclaredClass,
    externally_owned_account_class: DeclaredClass,
    account_proxy_class: DeclaredClass,
) -> StarknetContract:
    owner = 1
    class_hash = await starknet.deprecated_declare(
        source="./src/kakarot/kakarot.cairo",
        cairo_path=["src"],
        disable_hint_validation=True,
    )
    kakarot = await starknet.deploy(
        class_hash=class_hash.class_hash,
        constructor_calldata=[
            owner,  # owner
            eth.contract_address,  # native_token_address_
            contract_account_class.class_hash,  # contract_account_class_hash_
            externally_owned_account_class.class_hash,  # externally_owned_account_class_hash
            account_proxy_class.class_hash,  # account_proxy_class_hash
        ],
    )
    return kakarot


@pytest.fixture(scope="session")
def get_starknet_address(account_proxy_class, kakarot):
    """
    Fixture to return the starknet address of a contract deployed by kakarot.
    """

    def _factory(evm_contract_address):
        return calculate_contract_address_from_hash(
            salt=evm_contract_address,
            class_hash=account_proxy_class.class_hash,
            constructor_calldata=[],
            deployer_address=kakarot.contract_address,
        )

    return _factory


@pytest_asyncio.fixture(scope="session")
async def eth(starknet: Starknet):
    class_hash = await starknet.deprecated_declare(
        source="./tests/fixtures/ERC20.cairo"
    )
    return await starknet.deploy(
        class_hash=class_hash.class_hash,
        constructor_calldata=[
            int.from_bytes(b"Ether", "big"),  # name
            int.from_bytes(b"ETH", "big"),  # symbol
            18,  # decimals
        ],
    )


@pytest.fixture()
def starknet_snapshot(starknet):
    """
    Use this fixture to snapshot the starknet state before each test and reset it at teardown.
    """
    initial_state = starknet.state.copy()

    yield

    initial_cache_state = initial_state.state._copy()
    starknet.state.state = initial_cache_state


@pytest_asyncio.fixture(scope="session")
async def contract_account_class(starknet: Starknet) -> DeclaredClass:
    return await starknet.deprecated_declare(
        source="./src/kakarot/accounts/contract/contract_account.cairo",
        cairo_path=["src"],
        disable_hint_validation=True,
    )


@pytest_asyncio.fixture(scope="session")
async def externally_owned_account_class(starknet: Starknet):
    return await starknet.deprecated_declare(
        source="src/kakarot/accounts/eoa/externally_owned_account.cairo",
        cairo_path=["src"],
        disable_hint_validation=True,
    )


@pytest_asyncio.fixture(scope="session")
async def account_proxy_class(starknet: Starknet):
    return await starknet.deprecated_declare(
        source="src/kakarot/accounts/proxy/proxy.cairo",
        cairo_path=["src"],
        disable_hint_validation=True,
    )


@pytest_asyncio.fixture(scope="session")
def get_contract_account(starknet, contract_account_class):
    def _factory(starknet_address):
        return StarknetContract(
            starknet.state,
            contract_account_class.abi,
            starknet_address,
            None,
        )

    return _factory

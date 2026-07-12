.PHONY: contract-test worker-test swift-test xcode-test test verify package bootstrap

contract-test:
	python3 scripts/validate_worker_contract.py

worker-test:
	scripts/test_worker.sh

swift-test:
	scripts/test_swift.sh

xcode-test:
	scripts/test_xcode.sh

test: contract-test worker-test swift-test xcode-test

verify:
	scripts/verify_native_v1.sh

package:
	scripts/package_release.sh

bootstrap:
	scripts/bootstrap_worker.sh

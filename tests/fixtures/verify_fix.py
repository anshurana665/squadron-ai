import traceback
import tests.test_pipeline as tp

def verify_fix():
    try:
        tp.run_pipeline_tests()  # Assuming run_pipeline_tests() is the function causing the issue
        print("TEST PASSED")
    except Exception:
        print("TEST FAILED")
        traceback.print_exc()

verify_fix()


This script imports the `tests.test_pipeline` module and attempts to run the pipeline tests. If the tests pass, it prints "TEST PASSED". If the tests fail, it prints "TEST FAILED" and the full traceback.
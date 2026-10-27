import unittest

import launch


class LaunchCliTests(unittest.TestCase):
    def test_rejects_old_dev_prod_names(self):
        with self.assertRaises(SystemExit):
            launch.main(["dev"])
        with self.assertRaises(SystemExit):
            launch.main(["prod"])


if __name__ == "__main__":
    unittest.main()

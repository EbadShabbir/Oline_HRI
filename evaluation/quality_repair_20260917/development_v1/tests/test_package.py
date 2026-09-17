import unittest

import oline_hri


class PackageTests(unittest.TestCase):
    def test_version(self) -> None:
        self.assertEqual(oline_hri.__version__, "0.1.0")


if __name__ == "__main__":
    unittest.main()

import unittest
from calendar_bot import chunks_for_discord

class SplitTests(unittest.TestCase):
    def test_reassembles(self):
        text = 'First\n' + 'verylongword' * 600 + '\nLast'
        parts = chunks_for_discord(text)
        self.assertTrue(all(len(p) <= 1900 for p in parts))
        self.assertEqual(''.join(p.replace('\n', '') for p in parts), text.replace('\n', ''))

if __name__ == '__main__':
    unittest.main()

import unittest
from src.handlers.message_handler import _translate_to_khmer

class TestMessageHandler(unittest.TestCase):
    
    def test_translate_to_khmer_valid_crops(self):
        """Test if English crop names are correctly translated to Khmer."""
        self.assertEqual(_translate_to_khmer("Corn"), "ពោត")
        self.assertEqual(_translate_to_khmer("Mango"), "ស្វាយ")
        self.assertEqual(_translate_to_khmer("Rice"), "អង្ករ")
        self.assertEqual(_translate_to_khmer("Cucumber"), "ម្ទេស")  # Note: mapped to ម្ទេស in DB historically
        

        
    def test_translate_to_khmer_unknown_word(self):
        """Test if unknown words are returned as-is."""
        self.assertEqual(_translate_to_khmer("Apple"), "Apple")
        
    def test_translate_to_khmer_empty(self):
        """Test if empty strings return empty strings."""
        self.assertEqual(_translate_to_khmer(""), "")
        self.assertEqual(_translate_to_khmer(None), "")

if __name__ == '__main__':
    unittest.main()

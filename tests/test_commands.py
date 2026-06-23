import unittest
from unittest.mock import MagicMock
from src.handlers.message_handler import init_handler, handle_text_message

class TestBotCommands(unittest.TestCase):
    
    def setUp(self):
        # Create mock functions to track what the bot sends
        self.mock_send_fn = MagicMock()
        self.mock_update_fn = MagicMock()
        
        # Mock user state (always return IDLE state to allow commands to run)
        self.mock_get_user_fn = MagicMock(return_value={"state": "IDLE"})
        self.mock_db_conn_fn = MagicMock()
        self.mock_db_ready_fn = MagicMock(return_value=True)
        self.mock_bot_instance = MagicMock()
        
        # Initialize the handler with our mocks
        init_handler(
            send_fn=self.mock_send_fn,
            update_fn=self.mock_update_fn,
            get_user_fn=self.mock_get_user_fn,
            db_conn_fn=self.mock_db_conn_fn,
            db_ready_fn=self.mock_db_ready_fn,
            admin_ids=[999],
            phone_regex=None,
            bot_instance=self.mock_bot_instance
        )

    def _simulate_message(self, text):
        """Helper to simulate receiving a Telegram message."""
        message = {
            "chat": {"id": 123},
            "text": text,
            "from": {"first_name": "Test", "username": "testuser"}
        }
        # Call the main handler
        handle_text_message(
            message,
            get_user_stats_fn=MagicMock(),
            get_recent_users_fn=MagicMock(),
            format_datetime_fn=MagicMock()
        )

    def test_start_command(self):
        self.mock_get_user_fn.return_value = {"state": "START"}
        self._simulate_message("/start")
        self.mock_send_fn.assert_called()
        # Verify it asks for Name
        args, kwargs = self.mock_send_fn.call_args
        self.assertIn("សូមវាយ", args[1])

    def test_price_command(self):
        self._simulate_message("/price")
        self.mock_send_fn.assert_called()
        args, kwargs = self.mock_send_fn.call_args
        self.assertIn("ទីផ្សារ", args[1])

    def test_market_command(self):
        self._simulate_message("/market")
        self.mock_send_fn.assert_called()
        args, kwargs = self.mock_send_fn.call_args
        self.assertIn("ទីផ្សារលក់រាយ", args[1])

    def test_view_catalog_command(self):
        self._simulate_message("/view_catalog")
        self.mock_send_fn.assert_called()
        args, kwargs = self.mock_send_fn.call_args
        self.assertIn("កសិផល", args[1])

    def test_weather_command(self):
        self._simulate_message("/weather")
        self.mock_send_fn.assert_called()
        args, kwargs = self.mock_send_fn.call_args
        self.assertIn("អាកាសធាតុ", args[1])

    def test_location_command(self):
        self._simulate_message("/location")
        self.mock_send_fn.assert_called()
        args, kwargs = self.mock_send_fn.call_args
        self.assertIn("ទីតាំង", args[1])

if __name__ == '__main__':
    unittest.main()

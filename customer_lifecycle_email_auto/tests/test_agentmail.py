import os
import unittest


class AgentMailIntegrationTests(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("RUN_AGENTMAIL_INTEGRATION") == "1",
        "Set RUN_AGENTMAIL_INTEGRATION=1 and AgentMail credentials to run this live test.",
    )
    def test_agentmail_credentials_are_available_for_live_testing(self):
        self.assertTrue(os.environ.get("AGENTMAIL_API_KEY"))
        self.assertTrue(os.environ.get("AGENTMAIL_INBOX"))


if __name__ == "__main__":
    unittest.main()

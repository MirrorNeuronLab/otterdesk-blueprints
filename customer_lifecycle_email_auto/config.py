#!/usr/bin/env python3
import json
import os
import sys


def read_env_file(path):
    values = {}
    if not os.path.exists(path):
        return values
    with open(path, "r") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip()
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]
            values[key.strip()] = value
    return values


def main():
    print("Welcome to the Business Email Campaign Settings Setup!")
    print("This will configure your blueprint to use Ollama and AgentMail.")
    print("-" * 50)

    # Defaults
    default_llm_base = "http://192.168.4.173:11434"
    default_llm_model = "ollama/nemotron3:33b"
    default_test_email = "test@example.com"
    default_agentmail_inbox = "mn-demo@agentmail.to"
    default_agentmail_api = ""
    default_resend_from = ""
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    resend_env = read_env_file(
        os.path.join(repo_root, "mn-skills", "email_send_resend_skill", ".env")
    )
    agentmail_env = read_env_file(
        os.path.join(repo_root, "mn-skills", "email_receive_agentmail_skill", ".env")
    )
    default_agentmail_inbox = agentmail_env.get("AGENTMAIL_INBOX", default_agentmail_inbox)
    default_agentmail_api = agentmail_env.get("AGENTMAIL_API_KEY", default_agentmail_api)
    default_resend_from = resend_env.get("RESEND_FROM_EMAIL", default_resend_from)
    default_test_email = resend_env.get("RESEND_TEST_TO", default_test_email)

    # Prompts
    llm_base = input(f"Ollama API Base URL [{default_llm_base}]: ").strip() or default_llm_base
    llm_base = llm_base.rstrip("/")
    for suffix in ("/v1/chat/completions", "/v1"):
        if llm_base.endswith(suffix):
            llm_base = llm_base[: -len(suffix)]
    llm_model = input(f"Ollama Model [{default_llm_model}]: ").strip() or default_llm_model
    
    agentmail_inbox = input(f"AgentMail Inbox [{default_agentmail_inbox}]: ").strip() or default_agentmail_inbox
    agentmail_key_prompt = "AgentMail API Key [from .env]: " if default_agentmail_api else "AgentMail API Key []: "
    agentmail_key = input(agentmail_key_prompt).strip() or default_agentmail_api
    resend_key = input("Resend API Key (optional, used by email_send_resend_skill) [from .env]: ").strip() or resend_env.get("RESEND_API_KEY", "")
    resend_from = input(f"Resend From Email (optional) [{default_resend_from}]: ").strip() or default_resend_from

    test_mode = input("Enable Test Mode? (Send real emails to the test address as fast as each draft is ready) [Y/n]: ").strip().lower()
    is_test_mode = test_mode in ["", "y", "yes", "true"]
    
    test_email = ""
    if is_test_mode:
        test_email = input(f"Test Email Address [{default_test_email}]: ").strip() or default_test_email

    print("-" * 50)
    print("Updating manifest.json...")

    manifest_path = os.path.join(os.path.dirname(__file__), "manifest.json")
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    # Update nodes
    for node in manifest.get("nodes", []):
        if "config" in node and "environment" in node["config"]:
            env = node["config"]["environment"]
            
            # Update LLM Settings
            env["LITELLM_API_BASE"] = llm_base
            env["LITELLM_MODEL"] = llm_model
            env["LITELLM_API_KEY"] = env.get("LITELLM_API_KEY", "")
            for key in [
                "PRIMARY_LITELLM_API_KEY",
                "PRIMARY_LITELLM_API_BASE",
                "PRIMARY_LITELLM_MODEL",
                "SECONDARY_LITELLM_API_KEY",
                "SECONDARY_LITELLM_API_BASE",
                "SECONDARY_LITELLM_MODEL",
                "TERTIARY_LITELLM_API_BASE",
                "TERTIARY_LITELLM_MODEL",
                "LLM_API_KEY",
                "LLM_API_BASE",
                "LLM_MODEL",
                "OLLAMA_API_BASE",
                "GEMINI_API_KEY",
                "GEMINI_API_BASE_URL",
                "GEMINI_MODEL",
                "SYNAPTIC_LLM_CONFIG",
            ]:
                env.pop(key, None)
            
            # Update AgentMail Settings
            env["AGENTMAIL_API_KEY"] = agentmail_key
            env["AGENTMAIL_INBOX"] = agentmail_inbox
            env["RESEND_API_KEY"] = resend_key
            env["RESEND_FROM_EMAIL"] = resend_from
            env["SLACK_DEFAULT_CHANNEL"] = "#claw"
            for key in (
                "SLACK_BOT_TOKEN",
                "SLACK_API_BASE_URL",
                "MN_SLACK_BOT_TOKEN",
                "MN_SLACK_DEFAULT_CHANNEL",
                "MN_SLACK_API_BASE_URL",
            ):
                env.pop(key, None)
            
            if "GMAIL_ADDRESS" in env:
                del env["GMAIL_ADDRESS"]
            if "GMAIL_APP_PASSWORD" in env:
                del env["GMAIL_APP_PASSWORD"]
            if "GMAIL_SENDER_NAME" in env:
                del env["GMAIL_SENDER_NAME"]
            
            # Update Test Mode
            if is_test_mode:
                env["SYNAPTIC_TEST_EMAIL_TO"] = test_email
                env["SYNAPTIC_EMAIL_DELIVERY_MODE"] = "agentmail"
            else:
                env["SYNAPTIC_TEST_EMAIL_TO"] = ""
                env["SYNAPTIC_EMAIL_DELIVERY_MODE"] = "agentmail"

    for node in manifest.get("nodes", []):
        if node.get("node_id") == "monitor_scheduler_agent":
            node.setdefault("config", {})["fast_test_mode"] = is_test_mode
            node.setdefault("config", {})["interval_ms"] = 0 if is_test_mode else 300000

    # Mark as configured
    if "require_config" in manifest:
        manifest["require_config"] = False

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print("Success! The blueprint is now configured.")
    print("You can run it using: mn run customer_lifecycle_email_auto")

if __name__ == "__main__":
    main()

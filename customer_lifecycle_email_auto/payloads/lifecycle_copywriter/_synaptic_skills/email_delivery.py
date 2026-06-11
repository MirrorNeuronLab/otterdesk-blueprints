try:
    from mn_email_delivery_skill import dry_run_email, load_local_env, post_email, post_slack_message
except ModuleNotFoundError:
    import sys
    from pathlib import Path

    shared_skills_dir = Path(__file__).resolve().parents[2] / "_shared_skills"
    sys.path.insert(0, str(shared_skills_dir))
    from mn_email_delivery_skill import dry_run_email, load_local_env, post_email, post_slack_message

__all__ = ["dry_run_email", "load_local_env", "post_email", "post_slack_message"]

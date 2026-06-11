try:
    from gtm_outreach_skill import *  # noqa: F401,F403
except ModuleNotFoundError:
    import sys
    from pathlib import Path

    shared_skills_dir = Path(__file__).resolve().parents[2] / "_shared_skills"
    sys.path.insert(0, str(shared_skills_dir))
    from gtm_outreach_skill import *  # noqa: F401,F403

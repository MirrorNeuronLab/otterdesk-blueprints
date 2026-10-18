"""Compare completed response-budget experiments; never changes defaults or calls a model."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent / 'payloads'))
from domain.evaluation import evaluate  # noqa: E402
from domain.performance import measure  # noqa: E402


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--expected', type=Path, required=True)
    parser.add_argument('--baseline-review', type=Path)
    parser.add_argument('--candidate-review', type=Path)
    args = parser.parse_args()
    result = {name:{'performance':measure(root), 'accuracy_gate':evaluate(root, args.expected, review)}
        for name, root, review in [('baseline',args.baseline,args.baseline_review), ('candidate',args.candidate,args.candidate_review)]}
    result['decision'] = 'Keep defaults until both runs have source-valid outputs and substantive attorney-reviewed retention; missing overhead remains unknown.'
    if all(result[name]['accuracy_gate']['acceptance']=='passed' for name in ('baseline','candidate')):
        result['decision'] = 'Both supplied review gates pass. Compare measured stage times, response size and usage before proposing any default change; provider overhead may remain unknown.'
    print(json.dumps(result, indent=2))

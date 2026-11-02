import argparse
import json
from pathlib import Path

from .validation import inspect_package


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate an HR/CFS physical-data package without loading either engine")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("validate")
    check.add_argument("package", type=Path)
    check.add_argument("--source-root", type=Path, help="Also verify exported fingerprints against the source job")
    questions = sub.add_parser("questions", help="Write source-bound physical coordination questions")
    questions.add_argument("package", type=Path)
    questions.add_argument("--output", type=Path, required=True)
    answers = sub.add_parser("record-answers", help="Record explicitly accepted answers without releasing geometry")
    answers.add_argument("package", type=Path)
    answers.add_argument("questions", type=Path)
    answers.add_argument("answers", type=Path, help="JSON list with id, value, accepted=true and accepted_by")
    answers.add_argument("--output", type=Path, required=True)
    draw = sub.add_parser('draw',help='Generate a provisional coordination drawing set; open information requests do not block it')
    draw.add_argument('package',type=Path)
    draw.add_argument('--output',type=Path,required=True)
    args = parser.parse_args(argv)
    try:
        package = json.loads(args.package.read_text(encoding="utf-8-sig"))
        if args.command=='draw':
            from .drawing_workflow import initial_state,write_json,DrawingStore
            from .drawing_pdf import generate
            state=initial_state(package,1)
            report=generate(package,state,args.output)
            write_json(args.output/'state.json',state)
            write_json(args.output/'information_requests.json',DrawingStore.questions(state))
            print(json.dumps({'status':state['drawing_status'],'sheets':len(report['sheets']),'pdf':str(args.output/'drawings.pdf')}))
            return 0
        if args.command != "validate":
            from .review import questions as make_questions, record_answers
            if args.command == "questions": result=make_questions(package)
            else: result=record_answers(package,json.loads(args.questions.read_text(encoding='utf-8-sig')),json.loads(args.answers.read_text(encoding='utf-8-sig')))
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
            print(str(args.output))
            return 0
        verdict = inspect_package(package, args.source_root)
    except (OSError, ValueError) as ex:
        parser.exit(1, str(ex) + "\n")
    print(json.dumps(verdict, indent=2))
    return {"ready": 0, "needs_input": 2, "invalid": 1}[verdict["status"]]


if __name__ == "__main__":
    raise SystemExit(main())

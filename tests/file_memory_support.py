"""Offline FileMemory wire fixture; Rust tests own filesystem semantics."""
import hashlib
import grpc


class Exists(grpc.RpcError):
    def code(self):
        return grpc.StatusCode.ALREADY_EXISTS


class MemoryService:
    def __init__(self):
        self.scopes = {}
        self.calls = []

    def client(self, job_id, run_id, principal, **kwargs):
        service = self
        files = self.scopes.setdefault((job_id, run_id), {})

        class Client:
            def command(self, operation, **args):
                service.calls.append((operation, args, (job_id, run_id, principal)))
                result = {'version': 'mn.context.files.v1', 'operation': operation}
                if operation == 'init':
                    return result
                if operation == 'write':
                    if args['path'] in files:
                        raise Exists()
                    files[args['path']] = args['content']
                    return {**result, 'path': args['path'], 'file_version': digest(args['content'])}
                if operation == 'search':
                    words = set(args['query'].lower().split())
                    hits = [{'path': path, 'version': digest(text), 'line_start': 1}
                            for path, text in sorted(files.items()) if any(w in text.lower() for w in words)]
                    return {**result, 'results': hits[:args['limit']],
                            'files_scanned': len(files), 'incomplete': len(hits) > args['limit']}
                if operation == 'read':
                    text = files[args['path']]
                    lines = text.splitlines(keepends=True)
                    return {**result, 'path': args['path'], 'file_version': digest(text),
                            'content': ''.join(lines[args['start_line']-1:args['end_line']]),
                            'start_line': args['start_line'], 'end_line': min(args['end_line'], len(lines)),
                            'incomplete': False}
                raise AssertionError(operation)

            def close(self):
                pass

        return Client()


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()

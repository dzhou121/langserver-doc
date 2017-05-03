import neovim
import json
import subprocess
import time


@neovim.plugin
class Main(object):

    def __init__(self, vim):
        self.vim = vim
        self.job_id = 0
        self.execs = None
        self.procs = {}
        self.last_func_place = None
        self.last_pos = None
        self.last_result = None
        self.shown = False

    @neovim.function("_langserver_doc", sync=True)
    def init_python(self, args):
        self.vim.vars['langserver_doc#channel_id'] = self.vim.channel_id

    def init_execs(self):
        langserver_executables = self.vim.vars['langserver_executables']
        if isinstance(langserver_executables, dict):
            self.execs = langserver_executables
        else:
            self.execs = {}

    def echo(self, text):
        text = text.replace("'", " ")
        self.vim.command("echomsg '%s'" % text)

    def jsonrpc_send(self, proc, method, params={}):
        self.job_id = self.job_id + 1
        data = json.dumps({
            "jsonrpc": "2.0",
            "id": self.job_id,
            "method": method,
            "params": params,
        })
        proc.stdin.write('Content-Length: %s\r\n\r\n%s' % (len(data), data))

    def get_proc(self, filetype):
        if self.execs is None:
            self.init_execs()

        if filetype not in self.execs:
            return

        if filetype not in self.procs:
            file_exec = self.execs[filetype]
            cmd = ' '.join(file_exec['cmd'])
            self.procs[filetype] = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                # stderr=subprocess.PIPE,
                shell=True
            )

            params = {
                'capabilities': {},
                'rootPath': 'file:///Users',
            }
            self.jsonrpc_send(self.procs[filetype], 'initialize',
                              params=params)
            self.parse_output(self.procs[filetype])

        return self.procs[filetype]

    def document_update(self, proc, path, text):
        method = "textDocument/didChange"
        params = {
            "textDocument": {
                'uri': path,
            },
            "contentChanges": [{
                "text": text,
            }],
        }
        self.jsonrpc_send(proc, method, params)
        return self.parse_output(proc)

    @neovim.rpc_export('update', sync=False)
    def update(self, context):
        proc = self.get_proc(context['filetype'])
        if not proc:
            return

        self.echo("update succss")
        text = '\n'.join(self.vim.current.buffer[:])
        result = self.document_update(proc, context['filepath'], text)
        self.echo("update result" + json.dumps(result))

    def document_open(self, proc, path, text):
        method = "textDocument/didOpen"
        params = {
            "textDocument": {
                'uri': path,
                'text': text,
            },
        }
        self.jsonrpc_send(proc, method, params)
        return self.parse_output(proc)

    @neovim.rpc_export('open', sync=False)
    def open(self, context):
        proc = self.get_proc(context['filetype'])
        if not proc:
            return

        self.echo("open succss")
        text = '\n'.join(self.vim.current.buffer[:])
        result = self.document_open(proc, context['filepath'], text)
        self.echo("open result" + json.dumps(result))

    @neovim.rpc_export('clear', sync=False)
    def clear(self):
        if self.last_func_place is not None:
            self.last_func_place = None
            self.shown = False
            self.vim.call("rpcnotify", 0, "Gui", "signature_hide")

    def echo_comma(self, func_place):
        if not self.shown:
            return

        if func_place is None:
            return

        pos = func_place[2]
        if pos != self.last_pos:
            self.last_pos = pos
            # self.echo('__doccom__' + pos)
            self.vim.call("rpcnotify", 0, "Gui", "signature_pos", pos)

    def func_same(self, func_place):
        if func_place is None and self.last_func_place is None:
            return True

        if func_place is None and self.last_func_place is not None:
            return False

        if func_place is not None and self.last_func_place is None:
            return False

        return func_place[0] == self.last_func_place[0] and \
            func_place[1] == self.last_func_place[1]

    @neovim.rpc_export('request', sync=False)
    def request(self, context):
        if context['filetype'] != "go":
            return

        func_place = self.find_func(context['line'], context['col'])
        self.echo_comma(func_place)
        if self.func_same(func_place):
            return

        self.last_func_place = func_place

        if func_place is None:
            self.shown = False
            self.vim.call("rpcnotify", 0, "Gui", "signature_hide")
            return

        line, col, num_comma = func_place
        pos = self.vim.call("line2byte", line + 1) + col
        cmd = "godef -t -i -f %s -o %s" % (context['filepath'], pos)
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True
        )

        stdout_data, stderr_data = proc.communicate(
            '\n'.join(self.vim.current.buffer[:])
        )
        lines = stdout_data.split("\n")
        if len(lines) == 1:
            return

        self.shown = True
        self.vim.call("rpcnotify", 0, "Gui", "signature_show",
                      lines[1],
                      [line - context['line'], col - context['col']],
                      func_place[2])

    def old_request(self, context):
        proc = self.get_proc(context['filetype'])
        if not proc:
            return

        result = self.signature_help(proc, context['filepath'],
                                     context['line'], context['col'])
        result = result.get('result')
        if not result:
            result = ""

        if self.last_result != result:
            if result == "":
                self.echo("__doc__")
            else:
                self.echo("__doc__" + json.dumps(result))

            self.last_result = result

        return

        func_place = self.find_func(context['line'], context['col'])
        if self.last_func_place == func_place:
            return

        self.last_func_place = func_place

        if func_place is None:
            self.last_func_place = None
            self.echo("__doc__")
            return

        line, col, num_comma = func_place

        result = self.hover(proc, context['filepath'],
                            line, col)
        self.echo("result" + json.dumps(result))
        if 'result' not in result:
            self.last_func_place = None
            self.echo("__doc__")
            return

        exists = False
        result = result['result']
        contents = result.get('contents', [])
        if contents:
            exists = True
            resp = {
                'comma': num_comma,
                'contents': contents,
            }
            self.echo('__doc__' + json.dumps(resp))
            # content = contents[0].get('value')
            # if content:
            #     exists = True
            #     self.echo('__doc__' + str(num_comma) + " " + content)

        if not exists:
            self.last_func_place = None
            self.echo("__doc__")
        # if 'result' not in result:
        #     return

        # value = result['result'].get('contents', [])[0].get('value')
        # self.echo(value)

    def find_bracket(self, line, col, right=True):
        buf = self.vim.current.buffer
        num_comma = 0
        if right:
            height = len(buf)
            for l in range(line, height):
                cline = buf[l]
                s = 0
                if l == line:
                    s = col

                for c in range(s, len(cline)):
                    if cline[c] == "(":
                        return l, c, "("
                    elif cline[c] == ")":
                        return l, c, ")"
        else:
            for l in range(line, -1, -1):
                cline = buf[l]
                e = len(cline) - 1
                if l == line:
                    e = col - 1

                for c in range(e, -1, -1):
                    if cline[c] == "(":
                        return l, c, "(", num_comma
                    elif cline[c] == ")":
                        return l, c, ")", num_comma
                    elif cline[c] == ",":
                        num_comma += 1

    def find_func(self, line, col):
        result = self.find_bracket(line, col, False)
        if not result:
            return

        l, c, b, num_comma = result
        if b == ")":
            return
        else:
            return l, c - 1, num_comma
            # result = self.find_bracket(line, col, False)
            # if not result:
            #     return
            # l2, c2, b2, num_comma = result
            # if b2 == ")":
            #     return

            # return l2, c2, num_comma
        # else:
            # result = self.find_bracket(line, col, False)
            # if not result:
            #     return
            # l2, c2, b2, num_comma = result
            # if b2 == ")":
            #     return

            # return l2, c2, num_comma

        # orig_line = line
        # buf = self.vim.current.buffer
        # cline = buf[line]
        # line_length = len(cline)
        # found_right = False
        # for i in range(col, line_length):
            # if cline[i] == "(":
            #     return None
            # elif cline[i] == ")":
            #     found_right = True
            #     break

        # while not found_right:
            # line = line + 1
            # cline = buf[line]
            # line_length = len(cline)
            # for i in range(0, line_length):
            #     if cline[i] == "(":
            #         return None
            #     elif cline[i] == ")":
            #         found_right = True
            #         break

        # if not found_right:
            # return None

        # line = orig_line
        # cline = buf[line]
        # num_comma = 0
        # for i in range(col - 1, -1, -1):
            # if cline[i] == "(":
            #     return line, i - 1, num_comma
            # elif cline[i] == ",":
            #     num_comma += 1

        # found_left = False
        # while not found_left:
            # line = line - 1
            # cline = buf[line]
            # line_length = len(cline)
            # for i in range(line_length - 1, -1, -1):
            #     if cline[i] == "(":
            #         return line, i - 1, num_comma
            #     elif cline[i] == ",":
            #         num_comma += 1

        # return None

    def signature_help(self, proc, path, line, col):
        method = "textDocument/signatureHelp"
        params = {
            "textDocument": {
                'uri': path,
            },
            "position": {
                "line": line,
                "character": col,
            },
        }
        self.jsonrpc_send(proc, method, params)
        return self.parse_output(proc)

    def hover(self, proc, path, line, col):
        method = "textDocument/hover"
        params = {
            "textDocument": {
                'uri': path,
            },
            "position": {
                "line": line,
                "character": col,
            },
        }
        self.jsonrpc_send(proc, method, params)
        return self.parse_output(proc)

    def parse_output(self, proc):
        length = 0
        while True:
            buf = proc.stdout.read(7)
            if buf == "Content":
                remain = proc.stdout.readline()
                line = buf + remain
                if line.startswith("Content-Length: "):
                    length = int(line[16:])
            else:
                data = proc.stdout.read(length - 5)
                data = buf + data
                return json.loads(data)


if __name__ == "__main__":
    vim = neovim.attach("socket", path="/tmp/nvim")
    main = Main(vim)
    context = {
        "filetype": "go",
        "filepath": "file:///Users/Lulu/go/src/tardis/transport/tcp.go",
        "line": 20,
        "col": 65,
    }
    # main.open(context)
    main.request(context)

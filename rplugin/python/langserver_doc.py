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

    @neovim.rpc_export('clear', sync=False)
    def clear(self):
        if self.last_func_place is not None:
            self.last_func_place = None
            self.echo("__doc__")

    @neovim.rpc_export('request', sync=False)
    def request(self, context):
        if self.execs is None:
            self.init_execs()

        filetype = context['filetype']
        if filetype not in self.execs:
            return

        if filetype not in self.procs:
            file_exec = self.execs[filetype]
            cmd = ' '.join(file_exec['cmd'])
            print cmd
            self.procs[filetype] = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                # stderr=subprocess.PIPE,
                shell=True
            )

            params = {
                'capabilities': {},
                'rootPath': 'file:////',
            }
            self.jsonrpc_send(self.procs[filetype], 'initialize',
                              params=params)
            self.parse_output(self.procs[filetype])

        proc = self.procs[filetype]
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
        if 'result' not in result:
            self.last_func_place = None
            self.echo("__doc__")
            return

        exists = False
        result = result['result']
        contents = result.get('contents', [])
        if contents:
            content = contents[0].get('value')
            if content:
                exists = True
                self.echo('__doc__' + str(num_comma) + " " + content)

        if not exists:
            self.last_func_place = None
            self.echo("__doc__")
        # if 'result' not in result:
        #     return

        # value = result['result'].get('contents', [])[0].get('value')
        # self.echo(value)

    def find_func(self, line, col):
        orig_line = line
        buf = self.vim.current.buffer
        cline = buf[line]
        line_length = len(cline)
        found_right = False
        for i in range(col, line_length):
            if cline[i] == "(":
                return None
            elif cline[i] == ")":
                found_right = True
                break

        while not found_right:
            line = line + 1
            cline = buf[line]
            line_length = len(cline)
            for i in range(0, line_length):
                if cline[i] == "(":
                    return None
                elif cline[i] == ")":
                    found_right = True
                    break

        if not found_right:
            return None

        line = orig_line
        cline = buf[line]
        num_comma = 0
        for i in range(col - 1, -1, -1):
            if cline[i] == "(":
                return line, i - 1, num_comma
            elif cline[i] == ",":
                num_comma += 1

        found_left = False
        while not found_left:
            line = line - 1
            cline = buf[line]
            line_length = len(cline)
            for i in range(line_length - 1, -1, -1):
                if cline[i] == "(":
                    return line, i - 1, num_comma
                elif cline[i] == ",":
                    num_comma += 1

        return None

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
            print buf
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
    main.request({"filetype": "javascript", "filepath": "/", "line": 0, "col": 0})

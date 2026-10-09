"""Private existing publisher authentication; no token export or auth mutation."""
import json
import os
import re
import subprocess

from trusted_delivery import REPOSITORY


class UncertainAPI(OSError):
    pass


class GitHubAPI:
    def __call__(self,method,route,data=None):
        prefix='repos/'+REPOSITORY
        reads=[r'user',re.escape(prefix),re.escape(prefix)+r'/git/ref/heads/codex/pilot-admission',
               re.escape(prefix)+r'/git/ref/heads/deep-loop-pilot/[0-9a-f]{64}',
               re.escape(prefix)+r'/git/commits/[0-9a-f]{40}',
               re.escape(prefix)+r'/commits/[0-9a-f]{40}/check-runs\?per_page=100',
               re.escape(prefix)+r'/actions/runs/[1-9][0-9]*',
               re.escape(prefix)+r'/compare/[0-9a-f]{40}\.\.\.[0-9a-f]{40}',
               re.escape(prefix)+r'/pulls/[1-9][0-9]*',
               re.escape(prefix)+r'/pulls\?state=all&head=marcusgoll%3Adeep-loop-pilot%2F[0-9a-f]{64}&base=codex%2Fpilot-admission&per_page=100']
        writes=[prefix+'/'+suffix for suffix in ('git/blobs','git/trees','git/commits','git/refs','pulls')]
        if os.geteuid()!=0 or not (method=='GET' and any(re.fullmatch(pattern,route) for pattern in reads) or
                                   method=='POST' and route in writes):
            raise ValueError('Unapproved private publisher operation')
        args=['sudo','-n','-H','-u','orchestrator','/usr/bin/env',
              '-u','GH_TOKEN','-u','GITHUB_TOKEN','-u','GH_ENTERPRISE_TOKEN',
              '-u','GITHUB_ENTERPRISE_TOKEN','-u','GH_HOST','-u','GH_CONFIG_DIR',
              '--chdir=/home/orchestrator','/usr/bin/gh','api','--hostname','github.com',
              '--include','--method',method,route]
        payload=None
        if method=='POST':
            args+=['--input','-'];payload=json.dumps(data,allow_nan=False)
        elif data is not None:raise ValueError('Unexpected read request payload')
        try:
            result=subprocess.run(args,input=payload,capture_output=True,text=True,timeout=3)
        except (subprocess.TimeoutExpired,OSError) as exc:
            raise UncertainAPI('Private GitHub operation response unavailable') from exc
        if len(result.stdout.encode())>2*1024*1024:raise ValueError('Oversized GitHub response')
        header,separator,body=result.stdout.partition('\n\n')
        status=re.match(r'HTTP/\S+ (\d{3})\b',header)
        if not separator or status is None:raise UncertainAPI('Native GitHub response unavailable')
        code=int(status.group(1))
        if method=='GET' and code==404:return None
        if result.returncode!=0 or not 200<=code<300:
            raise UncertainAPI('Private GitHub operation did not confirm success')
        return json.loads(body)

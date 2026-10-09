"""Read only the independently accepted, stopped disposable artifact."""
import os
from pathlib import Path
import stat

from admission import digest
from artifact_verifier import ArtifactVerifier
from trusted_delivery import ARTIFACT
from resume_verifier import validate_resume_acceptance


class DeliveryArtifact:
    def __init__(self,candidate,owner_uid,store=None):
        self.candidate,self.owner_uid=Path(candidate),owner_uid
        self.store=store
    def __call__(self,contract,evidence):
        fresh=ArtifactVerifier(self.candidate,self.owner_uid)(contract,{'contract_digest':digest(contract)})
        if fresh!=evidence:raise ValueError('Stopped candidate acceptance changed before export')
        if 'resume_verification' in contract:
            if self.store is None:raise ValueError('Protected resume acceptance unavailable')
            validate_resume_acceptance(contract,evidence,self.store)
        fd=os.open(self.candidate,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            for part in ARTIFACT.split('/')[:-1]:
                child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                os.close(fd);fd=child
                if os.fstat(fd).st_uid!=self.owner_uid:raise ValueError('Foreign artifact directory')
            child=os.open(ARTIFACT.split('/')[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
            with os.fdopen(child,'rb') as stream:
                info=os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_uid!=self.owner_uid or info.st_nlink!=1:
                    raise ValueError('Untrusted stopped artifact')
                return stream.read(65537)
        finally:os.close(fd)

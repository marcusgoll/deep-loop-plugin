import unittest
from strict_configuration import UNKNOWN,validate_result

class StrictTests(unittest.TestCase):
    def test_positive_requires_clean_success(self):
        validate_result('positive','0','','')
        for status,stdout,stderr in [('25','',''),('1','',''),('0','rpc output',''),('0','','warning')]:
            with self.assertRaises(ValueError):validate_result('positive',status,stdout,stderr)
    def test_negative_requires_specific_unknown_field_rejection(self):
        validate_result('unknown_override','1','','Error: unknown field '+UNKNOWN)
        for status,stdout,stderr in [('0','',''),('1','','unsupported strict flag'),('25','',UNKNOWN),('1','','cannot write cache for '+UNKNOWN),('1','rpc output','unknown '+UNKNOWN)]:
            with self.assertRaises(ValueError):validate_result('unknown_override',status,stdout,stderr)

if __name__=='__main__':unittest.main()

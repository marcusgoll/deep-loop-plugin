import unittest
from strict_configuration import UNKNOWN,validate_result

class StrictTests(unittest.TestCase):
    def test_positive_requires_clean_success(self):
        validate_result('positive','0','','')
        for status,stdout,stderr in [('25','',''),('1','',''),('0','rpc output',''),('0','','warning')]:
            with self.assertRaises(ValueError):validate_result('positive',status,stdout,stderr)
    def test_only_exact_catalog_cancellation_can_accompany_zero_exit(self):
        diagnostic='2026-10-09T22:09:53.143043Z ERROR codex_models_manager::manager: failed to refresh available models: task 177 was cancelled\n'
        self.assertEqual(validate_result('positive','0','',diagnostic),'catalog_refresh_cancelled')
        colored='\x1b[2m2026-10-09T22:09:53.143043Z\x1b[0m \x1b[31mERROR\x1b[0m \x1b[2mcodex_models_manager::manager\x1b[0m\x1b[2m:\x1b[0m failed to refresh available models: task 177 was cancelled\n'
        self.assertEqual(validate_result('positive','0','',colored),'catalog_refresh_cancelled')
        for stderr in [diagnostic+'Error: unknown configuration\n',diagnostic*2,
                       diagnostic.replace('cancelled','failed'),diagnostic.replace('manager:', 'other:'),
                       diagnostic.replace('task 177', 'request 177'),diagnostic+'\x00']:
            with self.subTest(stderr=stderr):
                with self.assertRaises(ValueError):validate_result('positive','0','',stderr)
        with self.assertRaises(ValueError):validate_result('positive','1','',diagnostic)
        with self.assertRaises(ValueError):validate_result('unknown_override','1','',diagnostic)

    def test_negative_requires_specific_unknown_field_rejection(self):
        validate_result('unknown_override','1','','Error: unknown field '+UNKNOWN)
        for status,stdout,stderr in [('0','',''),('1','','unsupported strict flag'),('25','',UNKNOWN),('1','','cannot write cache for '+UNKNOWN),('1','rpc output','unknown '+UNKNOWN)]:
            with self.assertRaises(ValueError):validate_result('unknown_override',status,stdout,stderr)

if __name__=='__main__':unittest.main()

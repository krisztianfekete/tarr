import unittest
import mock
from tarr.test_case import DbTestCase, TarrApplicationTestCase

import tarr.cli as m # odule
import tarr.application
import tarr.model
from tarr.model import Job, Batch
import pickle
import tempdir
from StringIO import StringIO


TEST_CONNECTION_ARGS_LIST = '--ini test.ini --connection connection-tarr-test'.split()


# FIXME: tarr.cli: these tests are to be replaced with a test against a realistic, but simple test application (like one recording something known or easy to derive)
# actually this is the trivial way for testing parallel processing, but would also give more confidence for the command line module


class CommandWithArg(m.Command):

    def add_arguments(self, parser, defaults):
        parser.add_argument('--arg', type=int, default=defaults.get('arg'), help='an argument')


class Cli2(m.Cli):

    def get_commands(self):
        return [
            ('xcommand', m.Command, 'a command'),
            ('witharg', CommandWithArg, 'a command'),
        ]


class Test_Cli(unittest.TestCase):

    def test_description1(self):
        cli = m.Cli()
        self.assertIsNotNone(cli.parser.description)

    def test_description2(self):
        cli = m.Cli(description='desc2')
        self.assertEqual('desc2', cli.parser.description)

    def test_prog(self):
        cli = m.Cli()
        self.assertIsNotNone(cli.parser.prog)

    def test_prog2(self):
        cli = m.Cli(prog='prog2')
        self.assertEqual('prog2', cli.parser.prog)

    def test_subparsers(self):
        cli = m.Cli()
        help = cli.parser.format_help()
        self.assertIn('jobs', help)
        self.assertIn('create_job', help)
        self.assertIn('delete_job', help)

    def test_subparsers2(self):
        cli = Cli2()
        help = cli.parser.format_help()
        self.assertIn('xcommand', help)

    def test_parsed_command(self):
        cli = Cli2()
        self.assertEqual('xcommand', cli.parser.parse_args(['xcommand']).command)

    def test_parse_args(self):
        cli = Cli2()
        self.assertEqual(3, cli.parser.parse_args('witharg --arg=3'.split()).arg)

    def test_parse_args_defaults(self):
        self.assertEqual(2, Cli2(defaults=dict(arg=2)).parser.parse_args(['witharg']).arg)
        self.assertEqual(None, Cli2().parser.parse_args(['witharg']).arg)

    @unittest.skip('will not be implemented - it is individual commands that can decide on it')
    def test_parse_args_with_defaults(self):
        pass


class Test_Cli_parse_args(unittest.TestCase):

    def test_create_job(self):
        args = m.Cli().parse_args(
            (
                'create_job jobname --app=location.clean.Application --program=program-config --source=complex:rovat_13:pm'
                ' --partitioning_name=every_200'
            ).split()
            + ['--description=a description'])

        self.assertEqual('create_job', args.command)
        self.assertEqual('jobname', args.name)
        self.assertEqual('location.clean.Application', args.application)
        self.assertEqual('program-config', args.program)
        self.assertEqual('complex:rovat_13:pm', args.source)
        self.assertEqual('every_200', args.partitioning_name)
        self.assertEqual('a description', args.description)

    def test_delete_job(self):
        args = m.Cli().parse_args('delete_job jobname'.split())

        self.assertEqual('delete_job', args.command)
        self.assertEqual('jobname', args.name)

    def check_process_job(self, command):
        args = m.Cli().parse_args([command, 'jobname'])

        self.assertEqual(command, args.command)
        self.assertEqual('jobname', args.name)

    def test_process_job(self):
        self.check_process_job('process_job')

    def test_sequential_process_job(self):
        self.check_process_job('sequential_process_job')

    def test_parallel_process_job(self):
        self.check_process_job('parallel_process_job')

    def test_parsed_args_is_pickleable(self):
        args = m.Cli().parse_args('parallel_process_job jobname'.split())
        pickle.dumps(args)

    def test_process_batch(self):
        # parallel processing is working with pickle - or similar marshalling
        args = TEST_CONNECTION_ARGS_LIST + 'process_batch batch_id'.split()

        parsed_args = m.Cli().parse_args(args)

        pickled_args = pickle.dumps(parsed_args)
        unpickled_args = pickle.loads(pickled_args)

        self.assertEqual(parsed_args, unpickled_args)


class Test_Cli_main_integration(DbTestCase):

    def test_create_job(self):
        # setup schema in test database
        tarr.model.init(self.db_engine)
        tarr.model.init_meta_with_schema(tarr.model.meta)
        tarr.model.shutdown()

        args_list = (
            TEST_CONNECTION_ARGS_LIST
            + (
                'create_job jobname --app=tarr.application.Application'
                ' --program=tarr.fixtures.program'
                ' --source=complex:rovat_13:pm').split())

        m.Cli().main(args=args_list)

        with self.new_session() as session:
            job, = session.query(tarr.model.Job).all()
            self.assertEqual('jobname', job.job_name)


class CommandTestCase(TarrApplicationTestCase):

    def run_command(self, command_class, args):
        command = command_class()
        command.session = self.session
        command.run(args)
        command.session.rollback()
        command.session.close()


def demo_process_job_args(destdir, jobname):
    return m.Cli().parse_args(
        TEST_CONNECTION_ARGS_LIST
        + 'create_job --application tarr.demo_app.DemoApp --program tarr.demo_app'.split()
        + ['--source', destdir]
        + [jobname])

def process_job_args(jobname):
    return m.Cli().parse_args(
        TEST_CONNECTION_ARGS_LIST
        + ['process_job', jobname])

def statistics_args(jobname, dot=False):
    args = []
    if dot:
        args.append('--dot')
    args.append(jobname)
    return m.Cli().parse_args(
        TEST_CONNECTION_ARGS_LIST
        + ['statistics']
        + args)


TEXT_STATISTICS = '''   0 is_processed
       # True  -> 1   (*0)
       # False -> 1   (*90)
   1 set_processed
   2 is_processed
       # True  -> 3   (*90)
       # False -> 3   (*0)
   3 RETURN True   (*90)
END OF MAIN PROGRAM
'''

DOT_STATISTICS = '''digraph {

compound = true;

subgraph "cluster_None" {
    node_0 [label="is_processed"];
    node_0 -> node_1 [label="True: 0"];
    node_0 -> node_1 [label="False: 90"];
    node_1 [label="set_processed"];
    node_1 -> node_2;
    node_2 [label="is_processed"];
    node_2 -> node_3 [label="True: 90"];
    node_2 -> node_3 [label="False: 0"];
    node_3 [label="RETURN True: 90"];
}
}
'''

class Test_StatisticsCommand(CommandTestCase):

    def assert_output(self, expected_stdout, dot=False):
        with tempdir.TempDir() as destdir:
            jobname = 'jobname'
            self.run_command(m.CreateJobCommand, demo_process_job_args(destdir.name, jobname))
            self.run_command(m.ProcessJobCommand, process_job_args(jobname))

            stdout = StringIO()
            with mock.patch('sys.stdout', stdout):
                self.run_command(m.StatisticsCommand, statistics_args(jobname, dot=dot))

            self.assertEqual(expected_stdout.splitlines(), stdout.getvalue().splitlines())

    def test_text_output(self):
        self.assert_output(TEXT_STATISTICS)

    def test_dot_output(self):
        self.assert_output(DOT_STATISTICS, dot=True)


class Test_JobsCommand(CommandTestCase):

    def test(self):
        jobname1 = 'fancy_job_name1#@!{}$'
        jobname2 = 'fancy_job_name2#x>@!$'
        self.run_command(m.CreateJobCommand, demo_process_job_args('.', jobname1))
        self.run_command(m.CreateJobCommand, demo_process_job_args('.', jobname2))

        stdout = StringIO()
        with mock.patch('sys.stdout', stdout):
            jobs_args = m.Cli().parse_args(TEST_CONNECTION_ARGS_LIST + ['jobs'])
            self.run_command(m.JobsCommand, jobs_args)

        output = stdout.getvalue().splitlines()
        self.assertIn(jobname1, output)
        self.assertIn(jobname2, output)


def make_db_safe(command):
    command.session = mock.Mock()
    command.init_db = mock.Mock(command.init_db)
    command.shutdown = mock.Mock(command.shutdown)
    return command


def use_application(command, app):
    command.application = app

def mock_get_application(command, app):
    command.get_application = mock.Mock(command.get_application, side_effect=lambda application: use_application(command, app))

def mock_get_application_from_jobname(command, app):
    command.get_application_from_jobname = mock.Mock(command.get_application_from_jobname, side_effect=lambda jobname: use_application(command, app))

def mock_get_application_from_batchid(command, app):
    command.get_application_from_batchid = mock.Mock(command.get_application_from_batchid, side_effect=lambda jobname: use_application(command, app))

def args_mock():
    return mock.sentinel


class Test_CreateJobCommand(unittest.TestCase):

    def get_command(self):
        command = make_db_safe(m.CreateJobCommand())
        application_mock = mock.Mock(tarr.application.Application)
        application_mock.create_job = mock.Mock(tarr.application.Application.create_job)
        mock_get_application(command, application_mock)
        return command

    def test_parser(self):
        parser = m.argparse.ArgumentParser()
        self.get_command().add_arguments(parser, dict())

        args = parser.parse_args(
            (
                'jobname --app=location.clean.Application --program=program-config --source=complex:rovat_13:pm'
                ' --partitioning_name=every_200'
            ).split()
            + ['--description=a description'])

        self.assertEqual('jobname', args.name)
        self.assertEqual('location.clean.Application', args.application)
        self.assertEqual('program-config', args.program)
        self.assertEqual('complex:rovat_13:pm', args.source)
        self.assertEqual('every_200', args.partitioning_name)
        self.assertEqual('a description', args.description)

    def test_parser_defaults(self):
        parser = m.argparse.ArgumentParser()
        self.get_command().add_arguments(parser, dict(application='tarr.demo_app.DemoApp', program='tarr.demo_app', partitioning_name='dmeo'))

        args = parser.parse_args('jobname2 --source=complex:rovat_13:pm'.split())

        self.assertEqual('jobname2', args.name)
        self.assertEqual('tarr.demo_app.DemoApp', args.application)
        self.assertEqual('tarr.demo_app', args.program)
        self.assertEqual('complex:rovat_13:pm', args.source)
        self.assertEqual('dmeo', args.partitioning_name)
        self.assertEqual(None, args.description)

    def test_application_loading(self):
        command = self.get_command()

        command.run(args_mock())

        command.get_application.assert_called_once_with(mock.sentinel.application)

    def test_create_job(self):
        command = self.get_command()

        command.run(args_mock())

        command.application.create_job.assert_called_once_with(
            name=mock.sentinel.name,
            program_config=mock.sentinel.program,
            source=mock.sentinel.source,
            partitioning_name=mock.sentinel.partitioning_name,
            description=mock.sentinel.description)


class Test_DeleteJobCommand(unittest.TestCase):

    def get_command(self):
        command = make_db_safe(m.DeleteJobCommand())
        application_mock = mock.Mock(tarr.application.Application)
        application_mock.delete_job = mock.Mock(tarr.application.Application.delete_job)
        mock_get_application_from_jobname(command, application_mock)
        return command

    def test_job_loading(self):
        command = self.get_command()

        command.run(args_mock())

        command.get_application_from_jobname.assert_called_once_with(mock.sentinel.name)

    def test_delete_job(self):
        command = self.get_command()

        command.run(args_mock())

        command.application.delete_job.assert_called_once_with()


class Test_ProcessJobCommand(unittest.TestCase):

    def get_command(self):
        command = make_db_safe(m.ProcessJobCommand())
        application_mock = mock.Mock(tarr.application.Application)
        application_mock.process_job = mock.Mock(tarr.application.Application.process_job)
        mock_get_application_from_jobname(command, application_mock)
        return command

    def test_get_application_from_jobname(self):
        command = self.get_command()

        command.run(args_mock())

        command.get_application_from_jobname.assert_called_once_with(mock.sentinel.name)

    def test_load_program(self):
        command = self.get_command()

        command.run(args_mock())

        command.application.load_program.assert_called_once_with()

    def test_process_job(self):
        command = self.get_command()

        command.run(args_mock())

        command.application.process_job.assert_called_once_with()


class Test_ProcessBatchCommand(unittest.TestCase):

    def get_command(self):
        command = make_db_safe(m.ProcessBatchCommand())
        application_mock = mock.Mock(tarr.application.Application)
        application_mock.process_job = mock.Mock(tarr.application.Application.process_job)
        mock_get_application_from_batchid(command, application_mock)
        return command

    def test_process_batch(self):
        command = self.get_command()
        command.process_batch = mock.Mock(command.process_batch)

        command.run(args_mock())

        command.process_batch.assert_called_once_with(mock.sentinel.batch_id)

    def test_get_application_from_batchid(self):
        command = self.get_command()

        command.process_batch(mock.sentinel.batch_id)

        command.get_application_from_batchid.assert_called_once_with(mock.sentinel.batch_id)

    def test_load_program(self):
        command = self.get_command()

        command.process_batch(mock.sentinel.batch_id)

        command.application.load_program.assert_called_once_with()

    def test_app_process_batch(self):
        command = self.get_command()

        command.process_batch(mock.sentinel.batch_id)

        command.application.process_batch.assert_called_once_with()


def session_query_one_mock(return_value):
    query = mock.Mock()
    query.return_value = query
    query.filter = query
    query.one = mock.Mock(return_value=return_value)
    return query


class Test_Command_get_application_from_jobname(unittest.TestCase):

    def test(self):
        command = make_db_safe(m.Command())

        mock_application = mock.Mock(tarr.application.Application)
        mock_job = mock.Mock(Job)
        mock_job.get_application_instance = mock.Mock(Job.get_application_instance, return_value=mock_application)

        command.session.query = session_query_one_mock(return_value=mock_job)

        command.get_application_from_jobname('jobname')

        command.session.query.one.assert_called_once_with()
        mock_job.get_application_instance.assert_called_once_with()
        self.assertEqual(command.session, command.application.session)


class Test_Command_get_application_from_batchid(unittest.TestCase):

    def test(self):
        command = make_db_safe(m.Command())

        mock_application = mock.Mock(tarr.application.Application)
        mock_job = mock.Mock(Job)
        mock_job.get_application_instance = mock.Mock(Job.get_application_instance, return_value=mock_application)

        mock_batch = mock.Mock(Batch)
        mock_batch.job = mock_job

        command.session.query = session_query_one_mock(return_value=mock_batch)

        command.get_application_from_batchid(batch_id=None)

        command.session.query.one.assert_called_once_with()
        mock_job.get_application_instance.assert_called_once_with()
        self.assertEqual(mock_batch, command.application.batch)
        self.assertEqual(command.session, command.application.session)


class Test_InitCommand(DbTestCase):

    def setUp(self):
        super(Test_InitCommand, self).setUp()
        tarr.model.init(self.db_engine)

    def tearDown(self):
        tarr.model.shutdown()
        super(Test_InitCommand, self).tearDown()

    def test_Job_table_available(self):
        args = m.Cli().parse_args(TEST_CONNECTION_ARGS_LIST + ['init'])
        command = m.InitCommand()
        with self.new_session() as session:
            command.session = session
            command.run(args)

        job = tarr.model.Job()
        job.job_name = 'developer'
        job.application = 'typewriter'

        with self.new_session() as session:
            session.add(job)
            session.commit()
            session.expunge_all()

        with self.new_session() as session:
            job_from_db, = session.query(tarr.model.Job).all()

            self.assertIsNot(job, job_from_db)
            self.assertEqual('developer', job_from_db.job_name)
import base64
from django.conf import settings
from github import Github

from wtl.wtgithub.models import Repository
from wtl.wtlib.models import Project, Library, LibraryVersion, Language
from wtl.wtparser.parser import get_parser_for_filename


class WorkerError(BaseException):
    """
    Base class for all worker exceptions.
    """


class CantFindParserError(WorkerError):
    """
    Raised when can't find requirements file in given repository.
    """


class ParseError(WorkerError):
    """
    Raised when parser can't parse requirements file.
    """


class GithubWorker(object):
    github = None

    def __init__(self, github=None):
        super(GithubWorker, self).__init__()
        if github is None:
            github = Github(getattr(settings, 'WTGITHUB_USERNAME', None),
                            getattr(settings, 'WTGITHUB_PASSWORD', None))
        self.github = github

    def _get_repo(self, full_name):
        """
        Fetches GitHub repository information.
        """
        return self.github.get_repo(full_name)

    def _get_or_create_repository(self, rep):
        """
        Creates (if does not exist) and returns:
        `wtgithub.models.Repository` and `wtlib.models.Project`.
        """
        try:
            repository = Repository.objects.get(name=rep.name,
                                                owner=rep.owner._identity)
        except Repository.DoesNotExist:
            repository = Repository(name=rep.name, owner=rep.owner._identity)
        repository.starsCount = rep.watchers
        repository.description = rep.description
        repository.save()
        try:
            project = repository.project
        except Project.DoesNotExist:
            project = Project.objects.create(github=repository, name=rep.name)
        return repository, project

    def _get_parser_for_repository(self, rep):
        """
        Analyzes repository tree to find corresponding requirements parser.
        Currently analyzes only repository root and returns first matching
        parser. Raises `CantFindParserError` if can't determine parser for
        given repository.
        """
        tree = rep.get_git_tree('master')
        for node in tree.tree:
            if node.type != 'blob':
                continue
            parser = get_parser_for_filename(node.path)
            if parser is not None:
                return node.sha, parser
        raise CantFindParserError()

    def _parse_requirements(self, rep, blob_sha, parser):
        """
        Parses requirements file in given repository with given parser
        Raises `ParseError` if parse fails.
        """
        blob = rep.get_git_blob(blob_sha)
        if blob.encoding == 'utf-8':
            content = blob.content
        elif blob.encoding == 'base64':
            try:
                content = base64.b64decode(blob.content).decode('utf-8')
            except:
                raise ParseError('Error decoding blob')
        else:
            raise ParseError('Unknown blob encoding')
        try:
            return parser.parse(content)
        except:
            raise ParseError()

    def _save_parsed_requirements(self, project, parsed):
        """
        Saves parsed requirements to database.
        """
        language = Language.objects.get(name=parsed['language'])
        for package_dict in parsed['packages']:
            library, _ = Library.objects.get_or_create(
                language=language, name=package_dict['name'])
            version, _ = LibraryVersion.objects.get_or_create(
                library=library, version=package_dict['version'],
                version_special=package_dict['version_special'])
            version.save()
            project.libraries.add(version)

    def _update_user_counts(self, project):
        LibraryVersion.update_totals_by_project(project)

    def analyze_repo(self, full_name):
        rep = self._get_repo(full_name)
        repository, project = self._get_or_create_repository(rep)
        requirements_blob_sha, parser = self._get_parser_for_repository(rep)
        parsed = self._parse_requirements(rep, requirements_blob_sha, parser)
        self._save_parsed_requirements(project, parsed)
        self._update_user_counts(project)
        return repository, project

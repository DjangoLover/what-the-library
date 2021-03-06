from __future__ import unicode_literals
try:
    from functools import reduce
except ImportError:
    pass

from autoslug import AutoSlugField
from django.core.urlresolvers import reverse
from django.db import models
from django.utils.encoding import python_2_unicode_compatible
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _
from taggit.managers import TaggableManager

from wtl.wtgithub.models import Repository as GithubRepository


@python_2_unicode_compatible
class Language(models.Model):
    """
    Language

    A language. Programming language.
    """
    name = models.CharField(_('name'), max_length=128,
                            null=False, blank=False)
    slug = AutoSlugField(populate_from='name', unique=True)
    url_home = models.URLField(_('homepage URL'), max_length=1024,
                               null=False, blank=True, default='')
    color = models.CharField(_('color'), max_length=32, null=False, blank=True,
                             default="#ffffff")
    total_users = models.BigIntegerField(_('total number of users'),
                                         null=False, blank=True, default=0,
                                         editable=False, db_index=True)

    class Meta():
        ordering = ('-total_users',)
        verbose_name = _('language')
        verbose_name_plural = _('languages')

    def __str__(self):
        return self.name

    @classmethod
    def update_totals(cls):
        languages = cls.objects.annotate(count=models.Count('libraries'))
        for l in languages:
            l.total_users = l.count or 0
            l.save(update_fields=['total_users'])

    def get_absolute_url(self):
        return reverse('wtlib_libraries_list', args=[self.slug])

    def top_libraries(self):
        return self.libraries.filter(total_users__gt=0)[:5]


@python_2_unicode_compatible
class Library(models.Model):
    """
    Library

    This is what all this is about.
    """
    language = models.ForeignKey(Language, verbose_name=_('language'),
                                 related_name='libraries',
                                 null=False, blank=False)
    name = models.CharField(_('name'), max_length=512,
                            null=False, blank=False)
    slug = AutoSlugField(populate_from='name', unique_with=['language'])
    short_description = models.TextField()
    license = models.TextField()
    url_home = models.URLField(_('homepage URL'), max_length=1024,
                               null=False, blank=True, default='')
    url_docs = models.URLField(_('documentation URL'), max_length=1024,
                               null=False, blank=True, default='')
    url_repo = models.URLField(_('repository URL'), max_length=1024,
                               null=False, blank=True, default='')
    github = models.OneToOneField(GithubRepository, related_name='library',
                                  verbose_name=_('github'), blank=True,
                                  null=True)
    total_users = models.BigIntegerField(_('total number of users'),
                                         null=False, blank=True, default=0,
                                         editable=False, db_index=True)

    tags = TaggableManager()

    class Meta():
        ordering = ('-total_users',)
        verbose_name = _('library')
        verbose_name_plural = _('libraries')

    def __str__(self):
        return self.name

    @classmethod
    def update_totals(cls, project=None):
        # Not the best solution, but both my brain right now and Django ORM are
        # limited in their abilities.
        q = cls.objects.all()
        if project is not None:
            q = q.filter(id__in=project.libraries.values_list('library_id', flat=True))
        for l in q.annotate(count=models.Sum('versions__total_users')):
            l.total_users = l.count or 0
            l.save(update_fields=['total_users'])
        Language.update_totals()

    def projects(self):
        """
        Returns queryset for projects using this library
        """
        return Project.objects.filter(libraries__library=self)

    def often_used_with(self):
        """
        Returns queryset for libraries often used with this library
        Ordered by usage count
        """
        projects = self.projects
        libraries = Library.objects \
                .filter(versions__projects__in=projects) \
                .exclude(pk=self.pk) \
                .annotate(usage_count=models.Count('versions__id')) \
                .order_by('-usage_count', 'name')
        return libraries

    def get_absolute_url(self):
        return reverse('wtlib_library', args=[self.language.slug, self.slug])


@python_2_unicode_compatible
class LibraryVersion(models.Model):
    """
    Library Versions

    A library may have many versions. We need to keep that in mind, and in the
    database!
    """
    library = models.ForeignKey(Library, related_name='versions')
    version = models.CharField(_('version'), max_length=128,
                               null=True, blank=True)
    version_special = models.CharField(_('version special'), max_length=128,
                                       null=True, blank=True)
    release_date = models.DateField(null=True, blank=True, db_index=True)
    total_users = models.BigIntegerField(_('total number of users'),
                                         null=False, blank=True, default=0,
                                         editable=False)

    class Meta():
        ordering = ('-release_date',)
        verbose_name = _('library version')
        verbose_name_plural = _('library versions')

    def __str__(self):
        return '{0} {1}'.format(self.library.name, self.version)

    @classmethod
    def update_totals(cls, project=None):
        # Not the best solution, but both my brain right now and Django ORM are
        # limited in their abilities.
        q = cls.objects.all()
        if project is not None:
            q = q.filter(id__in=project.libraries.all)
        for v in q.annotate(count=models.Count('projects')):
            v.total_users = v.count or 0
            v.save(update_fields=['total_users'])
        Library.update_totals(project=project)


@python_2_unicode_compatible
class Project(models.Model):
    """
    Project

    Contains information about projects using libraries.
    """
    name = models.CharField(_('name'), max_length=512,
                            null=False, blank=False)
    slug = AutoSlugField(populate_from='name', unique=True)
    github = models.OneToOneField(GithubRepository, related_name='project',
                                  verbose_name=_('github'), blank=True,
                                  null=True)
    libraries = models.ManyToManyField(LibraryVersion,
                                       verbose_name=_('libraries'),
                                       related_name='projects')

    class Meta():
        verbose_name = _('project')
        verbose_name_plural = _('projects')

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('wtlib_project', args=[self.language_slug, self.slug])

    @cached_property
    def libs(self):
        return Library.objects.filter(pk__in=self.libraries.values_list('library_id'))

    def often_used_with(self):
        try:
            libraries = []
            for library in self.libraries.all():
                libraries +=library.library.often_used_with().exclude(pk__in=self.libs)
            def aggregate_library_usage(result, current):
                if result:
                    previous = result[-1]
                    if previous.pk == current.pk:
                        previous.usage_count += current.usage_count
                    else:
                        result.append(current)
                else:
                    result.append(current)
                return result
            # Sort libraries by id, so libraries with same id will go after each-other:
            # 1 1 3 5 5 6 7 8 8
            libraries = sorted(libraries, key=lambda l: l.id)
            # Now summ duplicate libraries usage count and remove duplicates
            libraries = reduce(aggregate_library_usage, libraries, [])
            # Order libraries by usage count
            libraries = sorted(libraries, key=lambda l: l.usage_count, reverse=True)
            return libraries
        except Exception as e:
            print(e)
            raise

    @property
    def language_slug(self):
        try:
            return self.libraries.all()[0].library.language.slug
        except IndexError:
            return None

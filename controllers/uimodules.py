import datetime
import math
import re
import tornado.template
import tornado.web
import urllib

from logic import content as content_logic
from logic import content_remote
from logic import url_factory

class Create(tornado.web.UIModule):
  def render(self, content=None, edit=False, individual_content=True):
    self.handler.display["individual_content"] = individual_content
    self.handler.display["content"] = content
    self.handler.display["edit"] = self.handler.get_argument('edit', False)
    self.handler.display["default_username"] = \
        self.handler.get_author_username()
    self.handler.display["remote_users"] = \
        self.handler.models.users_remote.get(
        local_username=self.handler.display["default_username"])[:]
    self.handler.display["sections"] = content_logic.get_sections_with_albums(
        self.handler, profile=self.handler.display["default_username"])
    self.handler.display["section_template"] = self.handler.get_argument(
        'section_template', None)
    self.handler.display["templates"] = self.handler.constants['templates']
    self.handler.display["section_cookie"] = self.handler.get_cookie("section")
    self.handler.display["album_cookie"] = self.handler.get_cookie("album")
    return self.render_string("_create.html", **self.handler.display)

class Moderate(tornado.web.UIModule):
  def render(self, item):
    self.handler.display["item"] = item
    self.handler.display["urlencode"] = urllib.urlencode
    return self.render_string("_moderate.html", **self.handler.display)

class SiteMap(tornado.web.UIModule):
  def render(self, content_owner, content=None, query=None):
    if type(content) is list and len(content):
      content = content[0]

    if content and content.section != 'main':
      profile = content.username
      section = content.section
      if content.album == 'main':
        album = content.name
      else:
        album = content.album
    else:
      profile = self.handler.breadcrumbs["profile"]
      section = self.handler.breadcrumbs["name"]
      album = None

    self.handler.display["sitemap"] = content_logic.get_sections_with_albums(
        self.handler, profile=profile, section=section, album=album)
    self.handler.display["content_owner"] = content_owner
    self.handler.display["content"] = content
    self.handler.display["query"] = query
    return self.render_string("_sitemap.html", **self.handler.display)


class Content(tornado.web.UIModule):
  def render(self, content, simple=True, template_type=None, sanitize=False):
    content.restricted = False
    content.is_remote = False

    content.comments_list = []
    if content.comments_count:
      content.comments_list = content_remote.get_comments(
          self.handler, content)
      is_forum = self.handler.display["section_template"] == 'forum'
      content.comments_list.sort(key=lambda x: x.date_created, reverse=(
          not is_forum))

    try:
      if not self.handler.authenticate(content=content,
          auto_login=(not simple)):
        if simple:
          content.restricted = True
          content.view = ('"You need to <a href="' +
              self.handler.nav_url(host=True, section="login") +
              '">login</a> to view this content.')
          return content
        else:
          raise tornado.web.HTTPError(401)
    except tornado.web.HTTPError as ex:
      if simple:
        content.restricted = True
        content.view = \
            '<span style="color:red">Sorry, you don\'t have access to view this content.</span>'
        return content
      else:
        # re-raise
        raise ex

    if sanitize:
      content.view = content_remote.sanitize(content.view)

    return content

class RemoteContent(tornado.web.UIModule):
  def render(self, content):
    content.restricted = False
    content.is_remote = True

    if content.comments_count:
      content.comments_list = self.handler.models.content_remote.get(
          to_username=content.to_username,
          thread=content.post_id,
          type='remote-comment')[:]
      for comment in content.comments_list:
        comment.is_remote = 1
      content.comments_list.sort(key=lambda x: x.date_created, reverse=True)
    else:
      content.comments_list = []

    return content

class ContentView(tornado.web.UIModule):
  def render(self, content, list_mode=False):
    self.handler.display["individual_content"] = type(content) is not list
    self.handler.display["referrer"] = content_remote.sanitize(
        self.handler.get_argument('referrer', ""))

    self.handler.display['favorites'] = []
    self.handler.display['list_mode'] = list_mode

    if not self.handler.display["individual_content"]:
      self.handler.display["feed"] = content
      for item in content:
        if item.is_remote:
          continue
        item.view = re.sub(r'(<[^<]*class="hw-read-more".*)', \
                              r'<a class="hw-read-more" href="' \
                              + self.handler.content_url(item) + r'">' \
                              + self.locale.translate('read more...') \
                          + r'</a>', \
                          item.view)
    else:
      self.handler.display["content"] = content

      if content.favorites:
        self.handler.display['favorites'] = \
            self.handler.models.content_remote.get(
              to_username=content.username,
              local_content_name=content.name,
              type='favorite')[:]

    return self.render_string("content.html", **self.handler.display)


class SimpleTemplate(tornado.web.UIModule):
  template_type = ""

  def render(self):
    if self.handler.breadcrumbs["name"] == 'main':
      raise tornado.web.HTTPError(404)

    collection, common_options = content_logic.get_collection(self.handler)

    if collection and self.template_type == 'slideshow':
      collection.reverse()

    self.handler.display["collection"] = [ self.handler.ui["modules"].Content(
        content, template_type=self.template_type) for content in collection ]

    if not collection:
      del common_options['redirect']
      section_options = { 'username' : self.handler.breadcrumbs["profile"],
                          'section' : 'main',
                          'name' : self.handler.breadcrumbs["name"], }
      album_options = { 'username' : self.handler.breadcrumbs["profile"],
                          'section' : self.handler.breadcrumbs["section"],
                          'album' : 'main',
                          'name' : self.handler.breadcrumbs["name"], }
      section_options = dict(common_options.items() + section_options.items())
      album_options = dict(common_options.items() + album_options.items())
      main_section = self.handler.models.content.get(
          **section_options).order_by('date_created', 'DESC')[:]
      main_album = self.handler.models.content.get(
          **album_options).order_by('date_created', 'DESC')[:]
      if not main_album and not main_section:
        raise tornado.web.HTTPError(404)

      return self.handler.fill_template("simple.html")
    else:
      return self.handler.fill_template(self.template_type + ".html")


class Album(SimpleTemplate):
  template_type = "album"

class Store(SimpleTemplate):
  template_type = "album"

class Forum(SimpleTemplate):
  template_type = "forum"

class Archive(SimpleTemplate):
  template_type = "archive"

# this template doesn't exist anymore, keep around class for
# backwards compatibility
class Links(SimpleTemplate):
  template_type = "album"

class Slideshow(SimpleTemplate):
  template_type = "slideshow"


class Feed(tornado.web.UIModule):
  template_type = "feed"

  def render(self):    
    if self.handler.breadcrumbs["name"] == 'main':
      raise tornado.web.HTTPError(404)

    is_owner_viewing = self.handler.is_owner_viewing(
        self.handler.breadcrumbs["profile"])

    if self.handler.breadcrumbs["section"] != 'main':
      content_options = { 'username': self.handler.breadcrumbs["profile"],
                          'section': self.handler.breadcrumbs["section"],
                          'album': self.handler.breadcrumbs["name"],
                          'forum': False,
                          'redirect': False, }
    elif self.handler.breadcrumbs["name"] != 'home':
      content_options = { 'username': self.handler.breadcrumbs["profile"],
                          'section': self.handler.breadcrumbs["name"],
                          'forum': False,
                          'redirect': False, }
    else:
      content_options = { 'username': self.handler.breadcrumbs["profile"],
                          #'section !=' : 'comments',
                          'forum': False,
                          'redirect': False, }

    if not is_owner_viewing:
      content_options['hidden'] = False

    is_reverse = False if self.template_type == 'events' else True
    self.handler.display["is_reverse"] = 1 if is_reverse else 0
    if is_reverse:
      count = self.handler.models.content.get(**content_options).count()
      default_offset = int(math.ceil(
          count / float(self.handler.constants['page_size'])))
    else:
      default_offset = 1
    offset = (int(self.handler.breadcrumbs["modifier"]) if
        self.handler.breadcrumbs["modifier"] else default_offset)
    offset -= 1
    begin  = self.handler.constants['page_size'] * offset
    end    = (self.handler.constants['page_size'] * offset +
        self.handler.constants['page_size'])

    if self.template_type == 'events':
      if self.handler.get_argument('past', ''):
        content_options['date_end <'] = datetime.datetime.utcnow()
      else:
        content_options['date_end >'] = datetime.datetime.utcnow()
      feed = self.handler.models.content.get(**content_options).order_by(
          'date_start')[begin:end]
    else:
      reverse_begin = max(count - end, 0)
      reverse_end = count - begin
      feed = self.handler.models.content.get(**content_options).order_by(
          'date_created', 'DESC')[reverse_begin:reverse_end]

    if (not feed and self.handler.request.headers.get("X-Requested-With") ==
        "XMLHttpRequest"):
      raise tornado.web.HTTPError(404)

    # todo, this should move to query really
    self.handler.display["feed"] = [ \
        self.handler.ui["modules"].Content(content) for \
        content in feed if content.section != 'main' and \
        content.album != 'main' ]
    self.handler.display["offset"] = offset + 1
    self.handler.display["is_event"] = self.template_type == "events"
    self.handler.display["page_size"] = self.handler.constants['page_size']

    if (self.handler.request.headers.get("X-Requested-With") ==
        "XMLHttpRequest"):
      self.handler.prevent_caching()
      self.handler.write(self.handler.ui["modules"].ContentView(
          self.handler.display["feed"]))
    else:
      if not feed:
        # TODO merge with SimpleTemplate
        section_options = { 'username' : self.handler.breadcrumbs["profile"],
                            'section' : 'main',
                            'name' : self.handler.breadcrumbs["name"], }
        album_options = { 'username' : self.handler.breadcrumbs["profile"],
                            'section' : self.handler.breadcrumbs["section"],
                            'album' : 'main',
                            'name' : self.handler.breadcrumbs["name"], }
        if not is_owner_viewing:
          section_options['hidden'] = False
          album_options['hidden'] = False

        main_section = self.handler.models.content.get(
            **section_options).order_by('date_created', 'DESC')[:]
        main_album = self.handler.models.content.get(
            **album_options).order_by('date_created', 'DESC')[:]

        if not main_album and not main_section:
          raise tornado.web.HTTPError(404)

        self.handler.fill_template("simple.html")
      else:
        self.handler.fill_template("content_feed.html")

class Events(Feed):
  template_type = "events"

class JumpTemplate(tornado.web.UIModule):
  template_type = ""

  def render(self):
    if self.handler.get_argument('mode', None) == 'archive':
      return self.ui["modules"]['Archive']()

    is_owner_viewing = self.handler.is_owner_viewing(
        self.handler.breadcrumbs["profile"])
    content_options = { 'username': self.handler.breadcrumbs["profile"],
                        'section': self.handler.breadcrumbs["name"],
                        'redirect': False, }
    if not is_owner_viewing:
      content_options['hidden'] = False

    if self.template_type == "latest":
      count = self.handler.models.content.get(**content_options).count()
      jump = self.handler.models.content.get(
          **content_options)[count - 1:count]
    else:
      jump = self.handler.models.content.get(**content_options)[0:1]

    if not jump:
      raise tornado.web.HTTPError(404)
      
    jump_url = self.handler.content_url(jump[0])

    if self.handler.display["edit"]:
      self.handler.display['redirect'] = jump_url
      self.handler.fill_template("redirect.html")
    else:
      self.handler.redirect(jump_url)

class First(JumpTemplate):
  template_type = "first"

class Latest(JumpTemplate):
  template_type = "latest"

class Blank(tornado.web.UIModule):
  def render(self):
    self.handler.fill_template("blank.html")

class Redirect(tornado.web.UIModule):
  def render(self):
    redirect = self.handler.models.content.get(
        username=self.handler.breadcrumbs["profile"],
        section=self.handler.breadcrumbs["section"],
        name=self.handler.breadcrumbs["name"])[0]

    if self.handler.display["edit"]:
      self.handler.display['redirect'] = redirect.view
      self.handler.fill_template("redirect.html")
    else:
      self.handler.redirect(redirect.view)

class StoreButton(tornado.web.UIModule):
  def render(self, item, content_owner):
    self.handler.display['mode'] = 'button'
    self.handler.display['item'] = item
    self.handler.display['content_owner'] = content_owner
    return self.render_string("store.html", **self.handler.display)

class StoreCheckout(tornado.web.UIModule):
  def render(self, item, content_owner):
    self.handler.display['mode'] = 'checkout'
    self.handler.display['item'] = item
    self.handler.display['content_owner'] = content_owner
    return self.render_string("store.html", **self.handler.display)

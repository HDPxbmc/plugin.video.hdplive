# -*- coding: utf-8 -*-
# default.py
# HDPfans Live TV
from xbmcswift2 import Plugin, xbmcgui, actions, CLI_MODE
import random
import urllib2
import re
from resources.lib.utils import keyboard, refresh
from resources.lib.player import Player, PlaybackFailed
from resources.lib.service import check_user, get_live_data, transform_classid

plugin = Plugin()


@plugin.route('/')
def index():
    notice_key = '10da88f4-c755-11e2-a78d-14dae9e9f059'
    cfg = plugin.get_storage('config')
    if cfg.get('last_notice_id') != notice_key:
        cfg['last_notice_id'] = notice_key
        try:
            cfg.sync()
        except:
            pass
        xbmcgui.Dialog().ok(u'友情提示：'.encode('utf-8'),
                            u'''\
通过 [COLOR FFFFFF00]点击鼠标右键、按遥控器菜单键、或平板电脑上长按屏幕[/COLOR]
可以 [COLOR FFFFFF00]选择信号源[/COLOR] 和 [COLOR FFFFFF00]收藏节目[/COLOR]。'''.encode('utf-8'))

    return [{
        'label': u'[COLOR FFFFFF00]收藏夹[/COLOR]',
        'path': plugin.url_for('list_favorites')
    }] + [{
        'label': tv_class['name'],
        'path': plugin.url_for('list_channels', class_id=tv_class['id']),
    } for tv_class in get_data()['class']] + [{
    #     'label': u'[COLOR FFFFFF00]私有直播[/COLOR]',
    #     'path': plugin.url_for('list_users'),
    # }, {
        'label': u'[COLOR FFFFFF00]刷新节目源[/COLOR] (间隔1小时自动刷新)',
        'path': plugin.url_for('clear_cache'),
        'is_playable': True,
        'properties': {'isPlayable': ''}
    }]


@plugin.route('/class/<class_id>/')
def list_channels(class_id):
    return make_channels_menu(get_data()['class_index'][class_id]['channels'])


@plugin.route('/try/<channel_id>/')
def try_sources(channel_id):
    channel = get_data()['channel_index'][channel_id]
    tvlinks = [{
        'name': link['name'],
        'link': link['link'],
        'index': i,
    } for i, link in enumerate(channel['tvlinks'])]
    tvlinks_count = len(tvlinks)

    last_index = plugin.get_storage('last_tvlink_indexes').get(channel_id, -1)
    if 0 <= last_index < tvlinks_count:
        last_link = tvlinks.pop(last_index)
        if tvlinks_count > 2:
            random.shuffle(tvlinks)
        tvlinks.insert(0, last_link)
    else:
        random.shuffle(tvlinks)
    # plugin.log.debug(tvlinks)

    try_play(tvlinks, channel['name'], channel_id)


@plugin.route('/choose/<channel_id>/')
def choose_source(channel_id):
    channel = get_data()['channel_index'][channel_id]
    tvlinks = channel['tvlinks']
    choice = xbmcgui.Dialog().select(u'选择信号源'.encode('utf-8'),
                                     [s['name'] for s in tvlinks])
    if choice < 0:
        return

    try:
        play_tv(tvlinks[choice]['link'], channel['name'], channel_id, choice)
    except PlaybackFailed:
        plugin.notify(u'您选择的信号源无法正常播放'.encode('utf-8'), delay=2000)


@plugin.route('/add_favorite/<channel_id>/')
def add_favorite(channel_id):
    # channel = get_data()['channel_index'][channel_id]
    favorites = plugin.get_storage('favorites')
    if channel_id in favorites:
        plugin.notify(u'您已经收藏过该频道'.encode('utf-8'), delay=2000)
    else:
        favorites[channel_id] = 1
        try:
            favorites.sync()
        except:
            plugin.log.debug('favorites storage save failed when add')
            plugin.notify(u'频道收藏过程中出现异常'.encode('utf-8'), delay=2000)
        else:
            plugin.notify(u'恭喜您频道收藏成功'.encode('utf-8'), delay=2000)


@plugin.route('/list_favorites/')
def list_favorites():
    favorites = plugin.get_storage('favorites')
    channels = get_data()['channel_index']
    items = [{
        'label': '[COLOR FFFF0000]已失效频道 [%s][/COLOR]' % ch_id if not ch else (
            '[COLOR FF00FF00]%s[/COLOR]' % ch['name'] if ch.get('diy')
            else ch['name']
        ),
        'path': plugin.url_for('remove_favorite', channel_id=ch_id) if not ch else (
            tvlinks[0]['link'] if len(tvlinks) == 1
            else plugin.url_for('try_sources', channel_id=ch_id)
        ),
        'is_playable': True,
        'properties': {'mimetype': 'video/x-msvideo', 'isPlayable': ''},
        'context_menu': [(
            u'[COLOR FFFFFF00]取消收藏[/COLOR]',
            actions.background(
                plugin.url_for('remove_favorite', channel_id=ch_id))
        ), (
            u'[COLOR FFFFFF00]选择信号源播放[/COLOR]',
            actions.background(
                plugin.url_for('choose_source', channel_id=ch_id))
        )],
        'replace_context_menu': True,
    } for ch_id, ch in
        sorted(
            ((ch_id, channels.get(ch_id)) for ch_id in favorites.iterkeys()),
            key=lambda x:x[1] and x[1]['name'] or x[0]
        )
        for tvlinks in (ch and ch['tvlinks'],)
    ]

    return items


@plugin.route('/remove_favorite/<channel_id>/')
def remove_favorite(channel_id):
    favorites = plugin.get_storage('favorites')
    if favorites.pop(channel_id, None):
        try:
            favorites.sync()
        except:
            plugin.log.debug('favorites storage save failed when remove')
            plugin.notify(u'频道删除过程中出现异常'.encode('utf-8'), delay=2000)
        else:
            plugin.notify(u'频道已成功删除'.encode('utf-8'), delay=2000)
            refresh()


@plugin.route('/users/')
def list_users():
    users = plugin.get_storage('users')
    return [{
        'label': userid,
        'path': plugin.url_for('show_user_classes', userid=userid),
        'context_menu': [(
            u'[COLOR FFFFFF00]删除帐号[/COLOR]',
            actions.background(
                plugin.url_for('remove_user', userid=userid))
            )],
        'replace_context_menu': True,
    } for userid in sorted(users.keys())] + [{
        'label': u'[COLOR FFFFFF00]添加帐号[/COLOR]',
        'path': plugin.url_for('add_user'),
        'is_playable': True,
        'properties': {'isPlayable': ''},
    }]


@plugin.route('/add_user/')
def add_user():
    userid = (keyboard(heading=u'请输入您在hdpfans.com的用户名或者UID') or '').strip()
    if (userid):
        users = plugin.get_storage('users')
        if userid in users:
            plugin.notify(u'用户已存在'.encode('utf-8'), delay=2000)
        elif check_user(userid):
            users[userid] = 1
            plugin.clear_function_cache()
            try:
                users.sync()
            except:
                plugin.log.debug('users storage save failed when add')
                plugin.notify(u'用户添加失败'.encode('utf-8'), delay=2000)
            else:
                plugin.notify(u'用户添加成功'.encode('utf-8'), delay=2000)
                refresh()
        else:
            plugin.notify(u'该用户没有收藏任何直播数据'.encode('utf-8'), delay=2000)


@plugin.route('/user/<userid>/')
def show_user_classes(userid):
    return [{
        'label': tv_class['name'],
        'path': plugin.url_for('show_user_channels',
                               userid=userid, class_id=tv_class['id']),
    } for tv_class in get_data()['users'][userid]]


@plugin.route('/user/<userid>/<class_id>/')
def show_user_channels(userid, class_id):
    channels = next(tv_class['channels']
                    for tv_class in get_data()['users'][userid]
                    if tv_class['id'] == class_id)
    return make_channels_menu(channels)


@plugin.route('/remove_user/<userid>/')
def remove_user(userid):
    users = plugin.get_storage('users')
    if users.pop(userid, None):
        plugin.clear_function_cache()
        try:
            users.sync()
        except:
            plugin.log.debug('users storage save failed when remove')
            plugin.notify(u'用户删除失败'.encode('utf-8'), delay=2000)
        else:
            plugin.notify(u'用户删除成功'.encode('utf-8'), delay=2000)
            refresh()


@plugin.route('/clear_cache/')
def clear_cache():
    plugin.clear_function_cache()
    plugin.notify(u'节目源数据更新完毕！'.encode('utf-8'))
    refresh()


def get_data():
    combine = CLI_MODE or plugin.get_setting('combine_user_resources', bool)
    return get_data_cached(combine)


@plugin.cached(60)
def get_data_cached(combine=False):
    data = get_live_data(plugin.get_storage('users').keys())
    if not combine:
        return data

    data_classes = data['class']
    class_index = data['class_index']

    # 合并数据
    for userid, user_data in data['users'].iteritems():
        for tv_class in user_data:
            clsid = transform_classid(tv_class['id'])
            if clsid in class_index:
                class_index[clsid]['channels'].extend(tv_class['channels'])
            else:
                data_classes.append(tv_class)
                class_index[clsid] = tv_class
    return data


def try_play(tvlinks, name='', channel_id=None):
    for tvlink in tvlinks:
        try:
            url = tvlink['link']
            plugin.log.debug(u'正在尝试播放节目源 %d [%s]： %s'.encode('utf-8'),
                             tvlink['index'] + 1, tvlink['name'], url)
            play_tv(url, name or tvlink['name'], channel_id, tvlink['index'])
            break
        except PlaybackFailed:
            plugin.notify((u'节目源[%s]不能正常播放，' % tvlink['name'])
                          .encode('utf-8'), delay=2000)
            continue
    else:
        plugin.notify(u'本频道暂时无法播放'.encode('utf-8'), delay=2000)


def play_tv(url, name, channel_id=None, index=None):
    listitem = xbmcgui.ListItem(name)
    listitem.setInfo(type="Video", infoLabels={'Title': name})

    # patch url
    if url.startswith('http://itv.hdpfans.com/ty/hdp_ty.php?uuid='):
        location = urllib2.urlopen(
            'http://proxy.shntv.cn/cntv-5-cctv1.m3u8').geturl()
        ip = re.compile(r'http:\/\/(.+?)[:\/]').match(location).group(1)
        url += '&ip=' + ip

    if url.startswith('http://live.hdpfans.com/'):
        url = urllib2.urlopen(url).geturl()

    player = Player()
    player.play(url, listitem)
    if channel_id is not None and index is not None:
        last_indexes = plugin.get_storage('last_tvlink_indexes')
        last_indexes[channel_id] = index
        try:
            last_indexes.sync()
        except:
            plugin.log.debug('last_tvlink_indexes storage save failed')


def make_channels_menu(channels):
    return [{
        'label': '[COLOR FF00FF00]%s[/COLOR]' % ch['name'] if ch.get('diy')
            else ch['name'],
        'path': ch['tvlinks'][0]['link'] if len(ch['tvlinks']) == 1 else
            plugin.url_for('try_sources', channel_id=ch['id']),
        'is_playable': True,
        'properties': {'mimetype': 'video/x-msvideo', 'isPlayable': ''},
        'context_menu': [(
            u'[COLOR FFFFFF00]选择信号源播放[/COLOR]',
            actions.background(
                plugin.url_for('choose_source', channel_id=ch['id']))
            ), (
                u'[COLOR FFFFFF00]添加到收藏夹[/COLOR]',
                actions.background(
                    plugin.url_for('add_favorite', channel_id=ch['id']))
            )],
        'replace_context_menu': True,
            } for ch in channels]

# copy from Plugin.run, remove storage save


def _run(self, test=False):
    '''The main entry point for a plugin.'''
    self._request = self._parse_request()
    # log.debug('Handling incoming request for %s', self.request.path)
    items = self._dispatch(self.request.path)

# Close any open storages which will persist them to disk
#    if hasattr(self, '_unsynced_storages'):
#        for storage in self._unsynced_storages.values():
#            log.debug('Saving a %s storage to disk at "%s"',
#                      storage.file_format, storage.filename)
#            storage.close()

    return items

if __name__ == '__main__':
    # plugin.run()
    _run(plugin)

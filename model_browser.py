# -*- coding: utf-8 -*-

from PA_runtime import *
import clr
clr.AddReference('System.Core')
clr.AddReference('System.Xml.Linq')
del clr

from System.IO import MemoryStream
from System.Text import Encoding
from System.Xml.Linq import *
from System.Linq import Enumerable
from System.Xml.XPath import Extensions as XPathExtensions

import os
import System
import sqlite3
import logging

SQL_CREATE_TABLE_BOOKMARK = '''
    CREATE TABLE IF NOT EXISTS bookmark(
        id INTEGER,
        time INTEGER,
        title TEXT,
        url TEXT,
        owneruser TEXT,
        source TEXT,
        deleted INTEGER,
        repeated INTEGER
    )'''

SQL_INSERT_TABLE_BOOKMARK = '''
    INSERT INTO bookmark(id, time, title, url, owneruser, source, deleted, repeated) values(? ,? ,? ,? ,? ,? ,?, ?)
    '''

SQL_CREATE_TABLE_SAVEPAGE = '''
    CREATE TABLE IF NOT EXISTS savepage(
        id INTEGER,
        time INTEGER,
        title TEXT,
        url TEXT,
        filename TEXT,
        filesize INTEGER,
        savepath TEXT,
        owneruser TEXT,
        source TEXT,
        deleted INTEGER,
        repeated INTEGER
    )'''

SQL_INSERT_TABLE_SAVEPAGE = '''
    INSERT INTO savepage(id, time, title, url, filename, filesize, savepath, owneruser, source, deleted, repeated) values(? ,? ,? ,? ,? ,? ,? ,? ,? ,?, ?)
    '''

SQL_CREATE_TABLE_SEARCHHISTORY = '''
    CREATE TABLE IF NOT EXISTS search_history(
        id INTEGER,
        name TEXT,
        url TEXT,
        datetime INTEGER,
        owneruser TEXT,
        source TEXT,
        deleted INTEGER,
        repeated INTEGER
    )'''

SQL_INSERT_TABLE_SEARCHHISTORY = '''
    INSERT INTO search_history(id, name, url, datetime, owneruser, source, deleted, repeated) values(? ,? ,? ,? ,? ,? ,?, ?)
    '''

SQL_CREATE_TABLE_DOWNLOADFILES = '''
    CREATE TABLE IF NOT EXISTS download_files(
        id INTEGER,
        url TEXT,
        filename TEXT,
        filefolderpath TEXT,
        totalsize INTEGER,
        createdate INTEGER,
        donedate INTEGER,
        costtime INTEGER,
        owneruser TEXT,
        source TEXT,
        deleted INTEGER,
        repeated INTEGER
    )'''

SQL_INSERT_TABLE_DOWNLOADFILES = '''
    INSERT INTO download_files(id, url, filename, filefolderpath, totalsize, createdate, donedate, costtime, owneruser, source, deleted, repeated) values(? ,?, ? ,? ,? ,? ,? ,? ,? ,? ,? ,?)
    '''

SQL_CREATE_TABLE_BROWSERECORDS = '''
    CREATE TABLE IF NOT EXISTS browse_records(
        id INTEGER,
        name TEXT,
        url TEXT,
        datetime INTEGER,
        owneruser TEXT,
        source TEXT,
        deleted INTEGER,
        repeated INTEGER
    )'''

SQL_INSERT_TABLE_BROWSERECORDS = '''
    INSERT INTO browse_records(id, name, url, datetime, owneruser, source, deleted, repeated) values(? ,? ,? ,? ,? ,? ,?, ?)
    '''

SQL_CREATE_TABLE_ACCOUNTS = '''
    CREATE TABLE IF NOT EXISTS accounts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        logindate INTEGER,
        source TEXT,
        deleted INTEGER,
        repeated INTEGER
    )'''

SQL_INSERT_TABLE_ACCOUNTS = '''
    INSERT INTO accounts(id, name, logindate, source, deleted, repeated) values(? ,? ,? ,? ,? ,?)
    '''

SQL_CREATE_TABLE_FILEINFO = '''
    CREATE TABLE IF NOT EXISTS file_info(
        id INTEGER,
        filepath TEXT,
        filename TEXT,
        size INTEGER,
        modifieddate INTEGER,
        title TEXT,
        owneruser TEXT,
        source TEXT,
        deleted INTEGER,
        repeated INTEGER
    )'''

SQL_INSERT_TABLE_FILEINFO = '''
    INSERT INTO file_info(id, filepath, filename, size, modifieddate, title, owneruser, source, deleted, repeated) values(? ,? ,? ,? ,? ,? ,? ,? ,?, ?)
    '''

SQL_CREATE_TABLE_PLUGIN = '''
    CREATE TABLE IF NOT EXISTS plugin(
        id INTEGER,
        title TEXT,
        url TEXT,
        packagename TEXT,
        packagesize INTEGER,
        isinstall INTEGER,
        installdate INTEGER,
        isdelete INTEGER,
        deletedate INTEGER,
        source TEXT,
        deleted INTEGER,
        repeated INTEGER
    )'''

SQL_INSERT_TABLE_PLUGIN = '''
    INSERT INTO plugin(id, title, url, packagename, packagesize, isinstall, installdate, isdelete, deletedate, source, deleted, repeated) values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'''

SQL_CREATE_TABLE_COOKIES = '''
    CREATE TABLE IF NOT EXISTS cookies(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        host_key TEXT,
        name TEXT,
        value TEXT,
        createdate INTEGER,
        expiredate INTEGER,
        lastaccessdate INTEGER,
        hasexipred INTEGER,
        owneruser TEXT,
        source TEXT,
        deleted INTEGER,
        repeated INTEGER
    )'''

SQL_INSERT_TABLE_COOKIES = '''
    INSERT INTO cookies(id, host_key, name, value, createdate, expiredate, lastaccessdate, hasexipred, owneruser, source, deleted, repeated) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'''

class MB(object):
    def __init__(self):
        self.db = None
        self.cursor = None

    def db_create(self,db_path):
        self.db_remove(db_path)
        self.db = sqlite3.connect(db_path)
        self.cursor = self.db.cursor()
        self.db_create_tables()

    def db_commit(self):
        if self.db is not None:
            self.db.commit()

    def db_close(self):
        if self.cursor is not None:
            self.cursor.close()
            self.cursor = None
        if self.db is not None:
            self.db.close()
            self.db = None

    def db_remove(self, db_path):
        if os.path.exists(db_path):
            os.remove(db_path)

    def db_create_tables(self):
        if self.cursor is not None:
            self.cursor.execute(SQL_CREATE_TABLE_ACCOUNTS)
            self.cursor.execute(SQL_CREATE_TABLE_BOOKMARK)
            self.cursor.execute(SQL_CREATE_TABLE_BROWSERECORDS)
            self.cursor.execute(SQL_CREATE_TABLE_DOWNLOADFILES)
            self.cursor.execute(SQL_CREATE_TABLE_FILEINFO)
            self.cursor.execute(SQL_CREATE_TABLE_SAVEPAGE)
            self.cursor.execute(SQL_CREATE_TABLE_SEARCHHISTORY)
            self.cursor.execute(SQL_CREATE_TABLE_PLUGIN)
            self.cursor.execute(SQL_CREATE_TABLE_COOKIES)

    def db_insert_table_accounts(self, Account):
        if self.cursor is not None:
            self.cursor.execute(SQL_INSERT_TABLE_ACCOUNTS, Account.get_values())

    def db_insert_table_bookmarks(self, Bookmark):
        if self.cursor is not None:
            self.cursor.execute(SQL_INSERT_TABLE_BOOKMARK, Bookmark.get_values())

    def db_insert_table_browserecords(self, BrowseRecord):
        if self.cursor is not None:
            self.cursor.execute(SQL_INSERT_TABLE_BROWSERECORDS, BrowseRecord.get_values())

    def db_insert_table_downloadfiles(self, DownloadFile):
        if self.cursor is not None:
            self.cursor.execute(SQL_INSERT_TABLE_DOWNLOADFILES, DownloadFile.get_values())

    def db_insert_table_fileinfos(self, FileInfo):
        if self.cursor is not None:
            self.cursor.execute(SQL_INSERT_TABLE_FILEINFO, FileInfo.get_values())

    def db_insert_table_savepages(self, SavePage):
        if self.cursor is not None:
            self.cursor.execute(SQL_INSERT_TABLE_SAVEPAGE, SavePage.get_values())

    def db_insert_table_searchhistory(self, SearchHistory):
        if self.cursor is not None:
            self.cursor.execute(SQL_INSERT_TABLE_SEARCHHISTORY, SearchHistory.get_values())

    def db_insert_table_plugin(self, Plugin):
        if self.cursor is not None:
            self.cursor.execute(SQL_INSERT_TABLE_PLUGIN, Plugin.get_values())

    def db_insert_table_cookies(self, Cookie):
        if self.cursor is not None:
            self.cursor.execute(SQL_INSERT_TABLE_COOKIES, Cookie.get_values())


class Column(object):
    def __init__(self):
        self.source = ''
        self.deleted = 0
        self.repeated = 0

    def __setattr__(self, name, value):
        if not IsDBNull(value):
            self.__dict__[name] = value

    def get_values(self):
        return (self.source, self.deleted, self.repeated)


class Account(Column):
    def __init__(self):
        super(Account, self).__init__()
        self.id = None
        self.name = None
        self.logindate = None

    def get_values(self):
        return (self.id, self.name, self.logindate) + super(Account, self).get_values()


class Bookmark(Column):
    def __init__(self):
        super(Bookmark, self).__init__()
        self.id = None
        self.time = None
        self.title = None
        self.url = None
        self.owneruser = 'default_user'

    def get_values(self):
        return (self.id, self.time, self.title, self.url, self.owneruser) + super(Bookmark, self).get_values()


class Browserecord(Column):
    def __init__(self):
        super(Browserecord, self).__init__()
        self.id = None
        self.name = None
        self.url = None
        self.datetime = None
        self.owneruser = 'default_user'

    def get_values(self):
        return (self.id, self.name, self.url, self.datetime, self.owneruser) + super(Browserecord, self).get_values()


class DownloadFile(Column):
    def __init__(self):
        super(DownloadFile, self).__init__()
        self.id = None
        self.url = None
        self.filename = None
        self.filefolderpath = None
        self.totalsize = None
        self.createdate = None
        self.donedate = None
        self.costtime = None
        self.owneruser = 'default_user'

    def get_values(self):
        return (self.id, self.url, self.filename, self.filefolderpath, self.totalsize, self.createdate, 
            self.donedate, self.costtime, self.owneruser) + super(DownloadFile, self).get_values()


class FileInfo(Column):
    def __init__(self):
        super(FileInfo, self).__init__()
        self.id = None
        self.filepath = None
        self.filename = None
        self.size = None
        self.modified = None
        self.title = None
        self.owneruser = 'default_user'

    def get_values(self):
        return (self.id, self.filepath, self.filename, self.size, self.modified, 
            self.title, self.owneruser) + super(FileInfo, self).get_values()


class SavePage(Column):
    def __init__(self):
        super(SavePage, self).__init__()
        self.id = None
        self.time = None
        self.title = None
        self.url = None
        self.filename = None
        self.filesize = None
        self.savepath = None
        self.owneruser = 'default_user'

    def get_values(self):
        return (self.id, self.time, self.title, self.url, self.filename, self.filesize,
            self.savepath, self.owneruser) + super(SavePage, self).get_values()


class SearchHistory(Column):
    def __init__(self):
        super(SearchHistory, self).__init__()
        self.id = None
        self.name = None
        self.url = None
        self.datetime = None
        self.owneruser = 'default_user'

    def get_values(self):
        return (self.id, self.name, self.url, self.datetime, self.owneruser) + super(SearchHistory, self).get_values()


class Plugin(Column):
    def __init__(self):
        super(Plugin, self).__init__()
        self.id = None
        self.title = None
        self.url = None
        self.packagename = None
        self.packagesize = None
        self.isinstall = None
        self.installdate = None
        self.isdelete = None
        self.deletedate = None

    def get_values(self):
        return (self.id, self.title, self.url, self.packagename, self.packagesize, self.isinstall, self.installdate, 
            self.isdelete, self.deletedate) + super(Plugin, self).get_values()


class Cookie(Column):
    def __init__(self):
        super(Cookie, self).__init__()
        self.id = None
        self.host_key = None
        self.name = None
        self.value = None
        self.createdate = None
        self.expiredate = None
        self.lastaccessdate = None
        self.hasexipred = None
        self.owneruser = None

    def get_values(self):
        return (self.id, self.host_key, self.name, self.value, self.createdate, self.expiredate, self.lastaccessdate,
            self.hasexipred, self.owneruser) + super(Cookie, self).get_values()


class Generate(object):

    def __init__(self, db_cache):
        self.db_cache = db_cache
        self.db = None
        self.cursor = None
        self.owneruser = 'default_user'

    def get_models(self):
        models = []
        self.db = sqlite3.connect(self.db_cache)
        self.cursor = self.db.cursor()
        models.extend(self._get_account_models())
        models.extend(self._get_bookmark_models())
        models.extend(self._get_browse_record_models())
        models.extend(self._get_downloadfile_models())
        models.extend(self._get_fileinfo_models())
        models.extend(self._get_savepage_models())
        models.extend(self._get_search_history_models())
        models.extend(self._get_plugin_models())
        models.extend(self._get_cookies_models())
        self.cursor.close()
        self.db.close()
        return models

    def _get_account_models(self):
        model = []
        sql = '''select distinct * from accounts group by name'''
        try:
            self.cursor.execute(sql)
            for row in self.cursor:
                canceller.ThrowIfCancellationRequested()
                user = Generic.User()
                if row[0] is not None:
                    user.Identifier.Value = str(row[0])
                if row[1] is not None:
                    user.Name.Value = row[1]
                if row[2] is not None:
                    user.TimeLastLogin.Value = self._get_timestamp(row[2])
                if row[3] not in [None, '']:
                    user.SourceFile.Value = self._get_source_file(row[3])
                if row[4] is not None:
                    user.Deleted = self._convert_deleted_status(row[4])
                model.append(user)
        except Exception as e:
            print(e)
        return model

    def _get_bookmark_models(self):
        model = []
        sql = '''select distinct * from bookmark'''
        try:
            self.cursor.execute(sql)
            for row in self.cursor:
                canceller.ThrowIfCancellationRequested()
                bookmark = Generic.WebBookmark()
                if row[1] is not None:
                    bookmark.TimeStamp.Value = self._get_timestamp(row[1])
                if row[2] is not None:
                    bookmark.Title.Value = row[2]
                if row[3] is not None:
                    bookmark.Url.Value = row[3]
                if row[5] not in [None, '']:
                    bookmark.SourceFile.Value = self._get_source_file(row[5])
                if row[6] is not None:
                    bookmark.Deleted = self._convert_deleted_status(row[6])
                model.append(bookmark)
        except Exception as e:
            print(e)
        return model

    def _get_browse_record_models(self):
        model = []
        sql = '''select distinct * from browse_records'''
        try:
            self.cursor.execute(sql)
            for row in self.cursor:
                canceller.ThrowIfCancellationRequested()
                visited = Generic.VisitedPage()
                if row[1] is not None:
                    visited.Title.Value = row[1]
                if row[2] is not None:
                    visited.Url.Value = row[2]
                if row[3] is not None:
                    visited.LastVisited.Value = self._get_timestamp(row[3])
                if row[5] not in [None, '']:
                    visited.SourceFile.Value = self._get_source_file(row[5])
                if row[6] is not None:
                    visited.Deleted = self._convert_deleted_status(row[6])
                model.append(visited)
        except Exception as e:
            print(e)
        return model

    def _get_downloadfile_models(self):
        model = []
        sql = '''select distinct * from download_files'''
        try:
            self.cursor.execute(sql)
            for row in self.cursor:
                canceller.ThrowIfCancellationRequested()
                download = Generic.Attachment()
                if row[1] is not None:
                    download.URL.Value = row[1]
                if row[3] is not None:
                    download.Filename.Value = row[3]  #因为下载文件有两个地址（下载地址和本地保存路径，于是把下载地址给了URL，本地地址给了Filename），本地地址用Filename储存时会警告文件名不合法，该问题正在解决
                if row[4] is not None:
                    download.Size.Value = row[4]
                if row[5] is not None:
                    download.DownloadTime.Value = self._get_timestamp(row[5])
                if row[9] not in [None, '']:
                    download.SourceFile.Value = self._get_source_file(row[9])
                if row[10] is not None:
                    download.Deleted = self._convert_deleted_status(row[10])
                model.append(download)
        except Exception as e:
            print(e)
        return model

    def _get_fileinfo_models(self):
        model = []
        sql = '''select distinct * from file_info'''
        try:
            self.cursor.execute(sql)
            for row in self.cursor:
                canceller.ThrowIfCancellationRequested()
                browseload = Generic.Attachment()
                if row[1] is not None:
                    browseload.URL.Value = row[1]
                if row[2] is not None:
                    browseload.Filename.Value = row[2]
                if row[3] is not None:
                    browseload.Size.Value = row[3]
                if row[5] is not None:
                    browseload.Title.Value = row[5]
                if row[6] not in [None, '']:
                    browseload.SourceFile.Value = self._get_source_file(row[6])
                if row[7] is not None:
                    browseload.Deleted = self._convert_deleted_status(row[7])
                model.append(browseload)
        except Exception as e:
            print(e)
        return model

    def _get_savepage_models(self):
        '''统一放到downloadfiles'''
        model = []
        return model

    def _get_search_history_models(self):
        model = []
        sql = '''select distinct * from search_history'''
        try:
            self.cursor.execute(sql)
            for row in self.cursor:
                canceller.ThrowIfCancellationRequested()
                search = Generic.Search()
                if row[2] is not None:
                    search.Content.Value = row[2]
                if row[3] is not None:
                    search.DateTime.Value = self._get_timestamp(row[3])
                if row[5] not in [None, '']:
                    search.SourceFile.Value = self._get_source_file(row[5])
                if row[6] is not None:
                    search.Deleted = self._convert_deleted_status(row[6])
                model.append(search)
        except Exception as e:
            print(e)
        return model

    def _get_plugin_models(self):
        '''插件没有相关模型类，暂时不作处理'''
        model = []
        sql = '''select distinct * from plugin'''
        return model

    def _get_cookies_models(self):
        model = []
        sql = '''select distinct * from cookies'''
        try:
            self.cursor.execute(sql)
            for row in self.cursor:
                canceller.ThrowIfCancellationRequested()
                cookie = Generic.Cookie()
                if row[1] is not None:
                    cookie.Domain.Value = row[1]
                if row[2] is not None:
                    cookie.Name.Value = row[2]
                if row[3] is not None:
                    cookie.Value.Value = row[3]
                if row[4] is not None:
                    cookie.CreationTime.Value = self._get_timestamp(row[4])
                if row[5] is not None:
                    cookie.Expiry.Value = self._get_timestamp(row[5])
                if row[6] is not None:
                    cookie.LastAccessTime.Value = self._get_timestamp(row[6])
                if row[7] not in [None, '']:
                    cookie.SourceFile.Value = self._get_source_file(str(row[7]))
                if row[8] is not None:
                    cookie.Deleted = self._convert_deleted_status(row[8])
                model.append(cookie)
        except Exception as e:
            print(e)
        return model

    @staticmethod
    def _convert_deleted_status(deleted):
        if deleted is None:
            return DeletedState.Unknown
        else:
            return DeletedState.Intact if deleted == 0 else DeletedState.Deleted

    def _get_source_file(self, source_file):
        if isinstance(source_file, str):
            return source_file.replace('/', '\\')
        return source_file

    def _get_timestamp(self, timestamp):
        try:
            if isinstance(timestamp, (long, float, str)) and len(str(timestamp)) > 10:
                timestamp = int(str(timestamp)[:10])
            if isinstance(timestamp, int) and len(str(timestamp)) == 10:
                ts = TimeStamp.FromUnixTime(timestamp, False)
                if not ts.IsValidForSmartphone():
                    ts = TimeStamp.FromUnixTime(0, False)
                return ts
        except:
            return TimeStamp.FromUnixTime(0, False)
    
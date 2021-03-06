#coding=utf-8
__author__ = "sumeng"

from PA_runtime import *
import clr
clr.AddReference('System.Core')
clr.AddReference('System.Xml.Linq')
clr.AddReference('System.Data.SQLite')
try:
    clr.AddReference('model_wechat')
    clr.AddReference('bcp_wechat')
    clr.AddReference('base_wechat')
except:
    pass
del clr

import System
from System.Linq import Enumerable
from System.Xml.XPath import Extensions as XPathExtensions
import System.Data.SQLite as SQLite

from PA.InfraLib.ModelsV2 import *

import os
import hashlib
import json
import string
import sqlite3
import shutil
import base64
import datetime
import model_wechat
import bcp_wechat
from base_wechat import *
import time
import gc

# EnterPoint: analyze_wechat(root, extract_deleted, extract_source):
# Patterns: '/DB/MM\.sqlite$'

# app数据库版本
VERSION_APP_VALUE = 4


def analyze_wechat(root, extract_deleted, extract_source):
    nodes = root.FileSystem.Search('/DB/MM\.sqlite$')
    if len(nodes) > 0:
        progress.Start()
        try:
            WeChatParser(process_nodes(nodes), extract_deleted, extract_source).process()
        except Exception as e:
            TraceService.Trace(TraceLevel.Error, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))
        progress.Finish(True)
    else:
        progress.Skip()

    pr = ParserResults()
    pr.Categories = DescripCategories.Wechat
    return pr


def process_nodes(nodes):
    # node:  /app_path/Documents/{user_hash}/DB/MM.sqlite
    ret = {}  # key: 节点名称  value: 节点对应的node数组
    app_dict = {}  # key: app路径  value: 节点名称
    app_tail = 1
    for node in nodes:
        try:
            user_node = node.Parent.Parent  # 获取{user_hash}
            try:
                app_node = user_node.Parent.Parent  # 获取app_path
            except Exception as e:
                app_node = None  # 没有包含app_path，可能是直接拷贝{user_hash}目录

            app_path = None
            app_info = None
            if app_node is not None:  # 如果能获取到app_path，从ds里获取app路径对应的app信息
                app_path = app_node.AbsolutePath
                try:
                    app_info = ds.GetApplication(app_node.AbsolutePath)
                except Exception as e:
                    pass
            else:
                app_path = user_node.AbsolutePath

            build = None
            if app_path in app_dict:
                build = app_dict.get(app_path, '微信')
            else:
                if app_info and app_info.Name:
                    build = app_info.Name.Value  # app_info里获取app名称
                    if build in app_dict:  # app名称如果和app_dict里的冲突，使用微信+数字的模式命名节点
                        build = None
                if build in [None, '']:  # 没有获取到app名称，使用微信+数字的模式命名节点
                    if app_tail < 2:
                        build = '微信'
                    else:
                        build = '微信' + str(app_tail)
                    app_tail += 1
                app_dict[app_path] = build

            value = ret.get(build, [])
            value.append(node)
            ret[build] = value
        except Exception as e:
            TraceService.Trace(TraceLevel.Error, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))
    return ret


def get_build(node):
    build = '微信'
    if node is None:
        return build
    app_path = node.AbsolutePath
    if app_path in [None, '']:
        return build
    try:
        info = ds.GetApplication(node.AbsolutePath)
        if info and info.Name:
            return info.Name.Value
    except Exception as e:
        TraceService.Trace(TraceLevel.Error, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))
    return build


class WeChatParser(Wechat):
    def __init__(self, node_dict, extract_deleted, extract_source):
        super(WeChatParser, self).__init__()
        self.node_dict = node_dict
        self.extract_deleted = extract_deleted
        self.extract_source = extract_source

    def process(self):
        for build in self.node_dict:
            prog = progress['APP', build]
            prog.Start()

            # 每个app创建一个资源节点
            self.ar = AppResources(build, DescripCategories.Wechat)
            self.ar.set_unique_id(build)
            self.ar.set_thum_config('pic_thum', 'Image')
            self.ar.set_thum_config('video_thum', 'Video')

            nodes = self.node_dict.get(build, [])
            for node in nodes:
                self.parse_user_node(node, build)
                gc.collect()

            #try:
            #    self.ar.parse()
            #except Exception as e:
            #    pass
            
            self.ar = None
            prog.Finish(True)

    def parse_user_node(self, node, build):
        self.im = model_wechat.IM()
        self.build = build
        self.models = []
        self.user_account = None
        self.user_account_model = None
        self.friend_models = {}
        self.chatroom_models = {}
        self.progress = None

        self.user_node = node.Parent.Parent
        try:
            self.app_node = self.user_node.Parent.Parent
        except Exception as e:
            self.app_node = None

        self.user_hash = self.get_user_hash()
        if self.app_node is not None:
            self.private_user_node = self.app_node.GetByPath('/Library/WechatPrivate/'+self.user_hash)
        else:
            self.private_user_node = None
        self.cache_path = os.path.join(ds.OpenCachePath('wechat'), self.get_user_guid())
        if not os.path.exists(self.cache_path):
            os.makedirs(self.cache_path)
        self.cache_db = os.path.join(self.cache_path, self.user_hash + '.db')
        save_cache_path(bcp_wechat.CONTACT_ACCOUNT_TYPE_IM_WECHAT, self.cache_db, ds.OpenCachePath("tmp"))

        if self.im.need_parse(self.cache_db, VERSION_APP_VALUE):
            #print('%s apple_wechat() parse begin' % time.asctime(time.localtime(time.time())))
            self.im.db_create(self.cache_db)

            self._generate_user_node_res()

            self.user_account = model_wechat.Account()
            self.models = []

            #print('%s apple_wechat() parse account' % time.asctime(time.localtime(time.time())))
            if not self._get_user_from_setting(self.user_node.GetByPath('mmsetting.archive')):
                self.user_account.account_id = self.user_hash
                self.user_account.insert_db(self.im)
                self.im.db_commit()
            self.user_account_model = self.get_account_model(self.user_account)
            self.add_model(self.user_account_model)
            self.progress = progress['APP', self.build]['ACCOUNT', self.user_account.account_id, self.user_account_model]
            self.progress.Start()

            #add self to friend
            if self.user_account is not None:
                model = WeChat.Friend()
                model.SourceFile = self.user_account.source
                model.Deleted = model_wechat.GenerateModel._convert_deleted_status(self.user_account.deleted)
                model.AppUserAccount = self.user_account_model
                model.Account = self.user_account.account_id
                model.NickName = self.user_account.nickname
                model.HeadPortraitPath = self.user_account.photo
                model.Gender = model_wechat.GenerateModel._convert_gender(self.user_account.gender)
                model.Signature = self.user_account.signature
                model.Type = WeChat.FriendType.Friend
                self.friend_models[self.user_account.account_id] = model
                self.add_model(model)
            self.push_models()
            self.set_progress(1)
            try:
                #print('%s apple_wechat() parse login device' % time.asctime(time.localtime(time.time())))
                self._parse_user_login_device_list(self.user_node.GetByPath('mmsetting.archive'))
            except Exception as e:
                TraceService.Trace(TraceLevel.Error, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))
            self.set_progress(2)
            try:
                #print('%s apple_wechat() parse WCDB_Contact.sqlite' % time.asctime(time.localtime(time.time())))
                self._parse_user_contact_db(self.user_node.GetByPath('/DB/WCDB_Contact.sqlite'))
            except Exception as e:
                TraceService.Trace(TraceLevel.Error, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))
            self.set_progress(10)
            try:
                #print('%s apple_wechat() parse WeAppV011.db' % time.asctime(time.localtime(time.time())))
                self._parse_user_app_db(self.user_node.GetByPath('/WeApp/DB/WeAppV011.db'))
            except Exception as e:
                TraceService.Trace(TraceLevel.Error, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))
            self.set_progress(11)
            try:
                #print('%s apple_wechat() parse contactlabel.list' % time.asctime(time.localtime(time.time())))
                self._parse_user_contact_label(self.user_node.GetByPath('contactlabel.list'))
            except Exception as e:
                TraceService.Trace(TraceLevel.Error, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))
            self.set_progress(12)
            try:
                self._parse_pay_card()
            except Exception as e:
                TraceService.Trace(TraceLevel.Error, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))
            self.set_progress(13)
            try:
                #print('%s apple_wechat() parse wc005_008.db' % time.asctime(time.localtime(time.time())))
                self._parse_user_wc_db(self.user_node.GetByPath('/wc/wc005_008.db'))
            except Exception as e:
                TraceService.Trace(TraceLevel.Error, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))
            self.set_progress(35)
            if self.private_user_node is not None:
                try:
                    #print('%s apple_wechat() parse fav.db' % time.asctime(time.localtime(time.time())))
                    self._parse_user_fav_db(self.private_user_node.GetByPath('/Favorites/fav.db'))
                except Exception as e:
                    TraceService.Trace(TraceLevel.Error, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))
                self.set_progress(41)
                try:
                    #print('%s apple_wechat() parse wshistory.pb' % time.asctime(time.localtime(time.time())))
                    self._parse_user_search(self.private_user_node.GetByPath('/searchH5/cache/wshistory.pb'))
                except Exception as e:
                    TraceService.Trace(TraceLevel.Error, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))
            self.set_progress(42)
            try:
                #print('%s apple_wechat() parse MM.sqlite' % time.asctime(time.localtime(time.time())))
                self._parse_user_mm_db(self.user_node.GetByPath('/DB/MM.sqlite'), 42, 87)
            except Exception as e:
                TraceService.Trace(TraceLevel.Error, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))
            self.set_progress(87)
            try:
                #print('%s apple_wechat() parse fts_message.db' % time.asctime(time.localtime(time.time())))
                self._parse_user_fts_db(self.user_node.GetByPath('/fts/fts_message.db'))
            except Exception as e:
                TraceService.Trace(TraceLevel.Error, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))
            self.set_progress(97)
            try:
                #print('%s apple_wechat() parse story_main.db' % time.asctime(time.localtime(time.time())))
                self._parse_user_story_db(self.user_node.GetByPath('/story/story_main.db'))
            except Exception as e:
                TraceService.Trace(TraceLevel.Error, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))
            self.set_progress(99)

            self._clear_user_node_res()

            self.im.db_create_index()
            # 数据库填充完毕，请将中间数据库版本和app数据库版本插入数据库，用来检测app是否需要重新解析
            if not canceller.IsCancellationRequested:
                self.im.db_insert_table_version(model_wechat.VERSION_KEY_DB, model_wechat.VERSION_VALUE_DB)
                self.im.db_insert_table_version(model_wechat.VERSION_KEY_APP, VERSION_APP_VALUE)

            self.im.db_commit()
            self.im.db_close()
            #print('%s apple_wechat() parse end' % time.asctime(time.localtime(time.time())))
            self.set_progress(100)
            self.progress.Finish(True)
        else:
            model_wechat.GenerateModel(self.cache_db, self.build, self.ar).get_models()

        self.ar.save_res_folder(self.user_node.GetByPath("Img"), "Image")
        self.ar.save_res_folder(self.user_node.GetByPath("Audio"), "Audio")
        self.ar.save_res_folder(self.user_node.GetByPath("Video"), "Video")
        self.ar.save_res_folder(self.user_node.GetByPath("OpenData"), "Other")
        if self.private_user_node is not None:
            self.ar.save_res_folder(self.private_user_node.GetByPath("Favorites/Data"), "Other")
            self.ar.save_res_folder(self.private_user_node.GetByPath("emoticonThumb"), "Image")
            self.ar.save_res_folder(self.private_user_node.GetByPath("emoticonPIC"), "Image")
            self.ar.save_res_folder(self.private_user_node.GetByPath("story/media_data"), "Video")

        self.im = None
        self.build = None
        self.models = None
        self.user_account = None
        self.user_account_model = None
        self.friend_models = None
        self.chatroom_models = None
        self.user_node = None
        self.app_node = None
        self.user_hash = None
        self.private_user_node = None
        self.cache_path = None

    def get_user_hash(self):
        path = self.user_node.AbsolutePath
        return os.path.basename(os.path.normpath(path))

    def get_user_guid(self):
        if self.app_node is not None:
            path = self.app_node.AbsolutePath
            return os.path.basename(os.path.normpath(path))
        else:
            return System.Guid.NewGuid().ToString('N')
    
    def _get_user_from_setting(self, user_plist):
        if user_plist is None:
            return False

        root = None
        try:
            root = BPReader.GetTree(user_plist)
        except Exception as e:
            return False
        if not root or not root.Children:
            return False

        self.user_account.account_id = self._bpreader_node_get_string_value(root, 'UsrName')
        self.user_account.account_id_alias = self._bpreader_node_get_string_value(root, 'AliasName')
        self.user_account.nickname = self._bpreader_node_get_string_value(root, 'NickName')
        self.user_account.gender = self._convert_gender_type(self._bpreader_node_get_int_value(root, 'Sex'))
        self.user_account.telephone = self._bpreader_node_get_string_value(root, 'Mobile')
        self.user_account.email = self._bpreader_node_get_string_value(root, 'Email')
        self.user_account.city = self._bpreader_node_get_string_value(root, 'City')
        self.user_account.country = self._bpreader_node_get_string_value(root, 'Country')
        self.user_account.province = self._bpreader_node_get_string_value(root, 'Province')
        self.user_account.signature = self._bpreader_node_get_string_value(root, 'Signature')

        if 'new_dicsetting' in root.Children:
            setting_node = root.Children['new_dicsetting']
            if 'headhdimgurl' in setting_node.Children:
                self.user_account.photo = self._bpreader_node_get_string_value(setting_node, 'headhdimgurl')
            else:
                self.user_account.photo = self._bpreader_node_get_string_value(setting_node, 'headimgurl')
            
        self.user_account.source = user_plist.AbsolutePath
        self.user_account.insert_db(self.im)
        self.im.db_commit()
        return True

    def _parse_user_login_device_list(self, user_plist):
        if user_plist is None:
            return False

        root = None
        try:
            root = BPReader.GetTree(user_plist)
        except Exception as e:
            return False
        if not root or not root.Children:
            return False

        if 'new_dicsetting' in root.Children:
            setting_node = root.Children['new_dicsetting']
            if 'LOGIN_DEVICE_LIST' in setting_node.Children:
                try:
                    devices = setting_node.Children['LOGIN_DEVICE_LIST']
                    for device in devices:
                        ld = model_wechat.LoginDevice()
                        ld.source = user_plist.AbsolutePath
                        ld.account_id = self.user_account.account_id
                        ld.id = self._bpreader_node_get_string_value(device, 'uuid')
                        ld.name = self._bpreader_node_get_string_value(device, 'name')
                        ld.type = self._bpreader_node_get_string_value(device, 'deviceType')
                        ld.last_time = self._bpreader_node_get_int_value(device, 'lastTime', None)
                        ld.insert_db(self.im)
                        self.add_model(self.get_login_device_model(ld))
                except Exception as e:
                    pass
                self.im.db_commit()
                self.push_models()
        return True

    def _parse_user_contact_db(self, node):
        if node is None:
            return False
        if canceller.IsCancellationRequested:
            return False
        try:
            db = SQLiteParser.Database.FromNode(node, canceller)
        except Exception as e:
            TraceService.Trace(TraceLevel.Error, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))
            return False
        if not db:
            return False

        if 'Friend' in db.Tables:
            ts = SQLiteParser.TableSignature('Friend')
            SQLiteParser.Tools.AddSignatureToTable(ts, "userName", SQLiteParser.FieldType.Text, SQLiteParser.FieldConstraints.NotNull)
            SQLiteParser.Tools.AddSignatureToTable(ts, "contact_remark", SQLiteParser.FieldType.Blob, SQLiteParser.FieldConstraints.NotNull)
            for rec in db.ReadTableRecords(ts, self.extract_deleted, False, ''):
                if canceller.IsCancellationRequested:
                    break
                if rec is None:
                    continue
                try:
                    username = self._db_record_get_string_value(rec, 'userName')
                    if username in [None, '']:
                        continue
                    contact_type = self._db_record_get_int_value(rec, 'type')
                    certification_flag = self._db_record_get_int_value(rec, 'certificationFlag')
                    contact_remark = self._db_record_get_blob_value(rec, 'dbContactRemark')
                    contact_head_image = self._db_record_get_blob_value(rec, 'dbContactHeadImage')
                    contact_chatroom = self._db_record_get_blob_value(rec, 'dbContactChatRoom')
                    contact_profile = self._db_record_get_blob_value(rec, 'dbContactProfile')
                    
                    deleted = 0 if rec.Deleted == DeletedState.Intact else 1
                    self._parse_user_contact_db_with_value(deleted, node.AbsolutePath, username, contact_type, certification_flag, contact_remark, contact_head_image, contact_chatroom, contact_profile)
                except Exception as e:
                    TraceService.Trace(TraceLevel.Debug, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))
            self.im.db_commit()
            self.push_models()

            self.get_chatroom_models(self.cache_db)
        return True

    def _parse_user_contact_db_with_value(self, deleted, source, username, contact_type, certification_flag, contact_remark, contact_head_image, contact_chatroom, contact_profile):
        nickname = None
        alias = None
        remark = None
        gender = None
        region = None
        signature = None
        if contact_remark is not None:
            nickname, alias, remark = self._process_parse_contact_remark(contact_remark)
        if contact_profile is not None:
            gender, region, signature = self._process_parse_contact_profile(contact_profile)

        head = None
        if self.private_user_node is not None:
            user_hash = self._md5(username)
            
            head = self._get_path_from_private_user_node_res('HeadImg/0/{}/{}.pic_hd'.format(user_hash[:2], user_hash[2:]))
            if head is None:
                head = self._get_path_from_private_user_node_res('HeadImg/0/{}/{}.pic_compressed'.format(user_hash[:2], user_hash[2:]))
        if head is None and contact_head_image is not None:
            head, head_hd = self._process_parse_contact_head(contact_head_image)
            if head_hd and len(head_hd) > 0:
                head = head_hd

        if username.endswith("@chatroom"):
            chatroom = model_wechat.Chatroom()
            chatroom.deleted = deleted
            chatroom.source = source
            chatroom.account_id = self.user_account.account_id
            chatroom.chatroom_id = username
            chatroom.name = nickname
            chatroom.photo = head
            chatroom.is_saved = contact_type % 2
            
            members, max_count = self._process_parse_group_members(contact_chatroom, deleted)
            for member in members:
                if canceller.IsCancellationRequested:
                    break
                try:
                    cm = model_wechat.ChatroomMember()
                    cm.deleted = deleted
                    cm.source = source
                    cm.account_id = self.user_account.account_id
                    cm.chatroom_id = username
                    cm.member_id = member.get('username')
                    cm.display_name = member.get('display_name')
                    cm.sp_id = chatroom.sp_id
                    cm.insert_db(self.im)
                except Exception as e:
                    TraceService.Trace(TraceLevel.Debug, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))

            if len(members) > 0:
                chatroom.owner_id = members[0].get('username')
            chatroom.insert_db(self.im)
        else:
            friend_type = model_wechat.FRIEND_TYPE_NONE
            if certification_flag != 0:
                friend_type = model_wechat.FRIEND_TYPE_OFFICIAL
            elif contact_type % 2 == 1:
                if self._parse_user_type_is_blocked(contact_type):
                    friend_type = model_wechat.FRIEND_TYPE_BLOCKED
                else:
                    friend_type = model_wechat.FRIEND_TYPE_FRIEND
            friend = model_wechat.Friend()
            friend.deleted = deleted
            friend.source = source
            friend.account_id = self.user_account.account_id
            friend.friend_id = username
            friend.friend_id_alias = alias
            friend.nickname = nickname
            friend.remark = remark
            friend.type = friend_type
            friend.photo = head
            friend.gender = self._convert_gender_type(gender)
            friend.region = region
            friend.signature = signature
            friend.insert_db(self.im)
            model = self.get_friend_model(friend)
            self.add_model(model)
            if deleted == 0 or username not in self.friend_models:
                self.friend_models[username] = model

    def _parse_user_contact_label(self, node):
        if node is None:
            return False

        root = None
        try:
            root = BPReader.GetTree(node)
        except Exception as e:
            return False
        if not root or not root.Children:
            return False

        for label_node in root.Children:
            value = label_node.Value
            cl = model_wechat.ContactLabel()
            cl.source = node.AbsolutePath
            cl.type = model_wechat.CONTACT_LABEL_TYPE_GROUP
            cl.account_id = self.user_account.account_id
            if 'm_uiID' in value.Children:
                cl.id = str(self._bpreader_node_get_int_value(value, 'm_uiID'))
            if 'm_nsName' in value.Children:
                cl.name = self._bpreader_node_get_string_value(value, 'm_nsName')
            cl.insert_db(self.im)
            self.add_model(self.get_contact_label_model(cl))
        self.im.db_commit()
        self.push_models()

        return True

    def _parse_user_mm_db(self, node, progress_start, progress_end):
        if not node:
            return False
        if canceller.IsCancellationRequested:
            return False

        tables = {}
        usernames = self.friend_models.keys() + self.chatroom_models.keys()
        for username in usernames:
            if canceller.IsCancellationRequested:
                break
            user_hash = self._md5(username)
            if user_hash is not None:
                table = 'Chat_' + user_hash
                tables[table] = username

        try:
            db = SQLiteParser.Database.FromNode(node, canceller)
        except Exception as e:
            TraceService.Trace(TraceLevel.Error, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))
            return False
        if not db:
            return False
        self.set_progress(progress_start+1)

        #db_tables = set()
        #ts = SQLiteParser.TableSignature('sqlite_master')
        #for rec in db.ReadTableRecords(ts, self.extract_deleted, False, ''):
        #    if canceller.IsCancellationRequested:
        #        break
        #    if rec is None:
        #        continue
        #    try:
        #        deleted = 0 if rec.Deleted == DeletedState.Intact else 1
        #        name = self._db_record_get_string_value(rec, 'name')
        #        db_type = self._db_record_get_string_value(rec, 'type')
        #        if name.startswith('Chat_') and db_type == 'table':
        #            db_tables.add(name)
        #            if deleted == 1:
        #                pass
        #    except Exception as e:
        #        TraceService.Trace(TraceLevel.Error, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))

        for i, table in enumerate(db.Tables):
            if canceller.IsCancellationRequested:
                break
            if not table.startswith('Chat_'):
                continue
            if table in tables:
                username = tables[table]
                user_unknown = False
            else:
                username = table[5:]
                user_unknown = True

            user_hash = table[5:]
            ts = SQLiteParser.TableSignature(table)
            SQLiteParser.Tools.AddSignatureToTable(ts, "Message", SQLiteParser.FieldType.Text, SQLiteParser.FieldConstraints.NotNull)
            SQLiteParser.Tools.AddSignatureToTable(ts, "Type", SQLiteParser.FieldType.Int)
            SQLiteParser.Tools.AddSignatureToTable(ts, "CreateTime", SQLiteParser.FieldType.Int, SQLiteParser.FieldConstraints.NotNull)
            for rec in db.ReadTableRecords(ts, self.extract_deleted, False, ''):
                if canceller.IsCancellationRequested:
                    break
                if rec is None:
                    continue
                try:
                    msg = self._db_record_get_string_value(rec, 'Message')
                    msg_type = self._db_record_get_int_value(rec, 'Type', MSG_TYPE_TEXT)
                    msg_local_id = self._db_record_get_string_value(rec, 'MesLocalID')
                    is_sender = 1 if self._db_record_get_int_value(rec, 'Des') == 0 else 0
                    timestamp = self._db_record_get_int_value(rec, 'CreateTime', None)
                    deleted = 0 if rec.Deleted == DeletedState.Intact else 1
                    self._parse_user_mm_db_with_value(deleted, node.AbsolutePath, username, msg, msg_type, msg_local_id, is_sender, timestamp, user_hash, user_unknown)
                except Exception as e:
                    TraceService.Trace(TraceLevel.Debug, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))
            self.im.db_commit()
            self.push_models()
            self.set_progress(progress_start+1 + i * 100 / len(db.Tables) * (progress_end - progress_start+1) / 100)

        for table in db.Tables:
            if canceller.IsCancellationRequested:
                break
            if table.startswith('Hello_'):
                ts = SQLiteParser.TableSignature(table)
                SQLiteParser.Tools.AddSignatureToTable(ts, "Message", SQLiteParser.FieldType.Text, SQLiteParser.FieldConstraints.NotNull)
                for rec in db.ReadTableRecords(ts, self.extract_deleted, False, ''):
                    if canceller.IsCancellationRequested:
                        break
                    if rec is None:
                        continue
                    try:
                        msg = self._db_record_get_string_value(rec, 'Message')
                        is_sender = 1 if self._db_record_get_int_value(rec, 'Des') == 0 else 0
                        timestamp = self._db_record_get_int_value(rec, 'CreateTime', None)
                        deleted = 0 if rec.Deleted == DeletedState.Intact else 1
                        self._parse_user_hello_db_with_value(deleted, node.AbsolutePath, msg, is_sender, timestamp)
                    except Exception as e:
                        TraceService.Trace(TraceLevel.Debug, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))
                self.im.db_commit()
                self.push_models()
        return True

    def _parse_user_mm_db_with_value(self, deleted, source, username, msg, msg_type, msg_local_id, is_sender, timestamp, user_hash, user_unknown):
        revoke_content = None
        message = model_wechat.Message()
        message.deleted = deleted
        message.source = source
        message.account_id = self.user_account.account_id
        message.talker_id = username
        message.msg_id = msg_local_id
        message.type = self._convert_msg_type(msg_type)
        message.timestamp = timestamp
        if user_unknown:
            message.talker_type = model_wechat.CHAT_TYPE_NONE
            message.sender_id = self.user_account.account_id if is_sender else username
            revoke_content = self._process_parse_group_message(msg, msg_type, msg_local_id, is_sender, user_hash, message)
        elif username.endswith("@chatroom"):
            message.talker_type = model_wechat.CHAT_TYPE_GROUP
            self._process_parse_group_message(msg, msg_type, msg_local_id, is_sender, user_hash, message)
        else:
            message.talker_type = model_wechat.CHAT_TYPE_FRIEND
            message.sender_id = self.user_account.account_id if is_sender else username
            if username == 'newsapp':
                message.content = self._process_parse_message_tencent_news(msg, message)
            else:
                revoke_content = self._process_parse_friend_message(msg, msg_type, msg_local_id, user_hash, message)

        message.insert_db(self.im)
        model, tl_model = self.get_message_model(message)
        self.add_model(model)
        self.add_model(tl_model)

        if revoke_content is not None:
            revoke_message = model_wechat.Message()
            revoke_message.IsRecall = True
            revoke_message.deleted = message.deleted
            revoke_message.source =  message.source
            revoke_message.account_id = message.account_id
            revoke_message.talker_id = message.talker_id
            revoke_message.talker_type = message.talker_type
            revoke_message.msg_id = message.msg_id
            revoke_message.timestamp = message.timestamp
            revoke_message.type = model_wechat.MESSAGE_CONTENT_TYPE_TEXT
            revoke_message.sender_id = self.user_account.account_id
            revoke_message.content = revoke_content
            revoke_message.insert_db(self.im)
            model, tl_model = self.get_message_model(revoke_message)
            self.add_model(model)
            self.add_model(tl_model)

    def _parse_user_hello_db_with_value(self, deleted, source, msg, is_sender, timestamp):
        user_model, content = self._parse_user_hello_xml(deleted, source, msg)
        if user_model is not None:
            message = model_wechat.Message()
            message.deleted = deleted
            message.source = source
            message.account_id = self.user_account.account_id
            message.type = model_wechat.MESSAGE_CONTENT_TYPE_TEXT
            message.timestamp = timestamp
            message.talker_id = user_model.Account
            message.talker_type = model_wechat.CHAT_TYPE_FRIEND
            message.sender_id = self.user_account.account_id if is_sender else user_model.Account
            message.content = content
            message.insert_db(self.im)
            model, tl_model = self.get_message_model(message)
            self.add_model(model)
            self.add_model(tl_model)

    def _parse_user_hello_xml(self, deleted, source, xml_str):
        xml = None
        user_model = None
        content = None
        try:
            xml = XElement.Parse(xml_str)
        except Exception as e:
            if deleted == 0:
                TraceService.Trace(TraceLevel.Debug, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))
        if xml is not None:
            if xml.Attribute('content'):
                content = xml.Attribute('content').Value
            if xml.Attribute('fromusername'):
                username = xml.Attribute('fromusername').Value
                if username in self.friend_models:
                    user_model = self.friend_models.get(username)
                else:
                    friend = model_wechat.Friend()
                    friend.deleted = deleted
                    friend.source = source
                    friend.account_id = self.user_account.account_id
                    friend.friend_id = username
                    if xml.Attribute('alias'):
                        friend.friend_id_alias = xml.Attribute('alias').Value
                    if xml.Attribute('fromnickname'):
                        friend.nickname = xml.Attribute('fromnickname').Value
                    friend.type = model_wechat.FRIEND_TYPE_NONE
                    if xml.Attribute('bigheadimgurl'):
                        friend.photo = xml.Attribute('bigheadimgurl').Value
                    elif xml.Attribute('smallheadimgurl'):
                        friend.photo = xml.Attribute('smallheadimgurl').Value
                    if xml.Attribute('sex'):
                        try:
                            friend.gender = self._convert_gender_type(int(xml.Attribute('sex').Value))
                        except Exception as e:
                            pass
                    if xml.Attribute('sign'):
                        friend.signature = xml.Attribute('sign').Value
                    friend.insert_db(self.im)
                    user_model = self.get_friend_model(friend)
                    self.add_model(user_model)
                    self.friend_models[username] = user_model
        return user_model, content

    def _parse_user_wc_db(self, node):
        if node is None:
            return False
        if canceller.IsCancellationRequested:
            return False

        try:
            db = SQLiteParser.Database.FromNode(node, canceller)
        except Exception as e:
            TraceService.Trace(TraceLevel.Error, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))
            return False
        if not db:
            return False

        tables = [t for t in db.Tables if t.startswith('MyWC01_')]
        for table in tables:
            if canceller.IsCancellationRequested:
                break
            ts = SQLiteParser.TableSignature(table)
            SQLiteParser.Tools.AddSignatureToTable(ts, "FromUser", SQLiteParser.FieldType.Text, SQLiteParser.FieldConstraints.NotNull)
            SQLiteParser.Tools.AddSignatureToTable(ts, "Buffer", SQLiteParser.FieldType.Blob, SQLiteParser.FieldConstraints.NotNull)
            
            for rec in db.ReadTableRecords(ts, self.extract_deleted, False, ''):
                if canceller.IsCancellationRequested:
                    break
                if rec is None:
                    continue
                try:
                    username = self._db_record_get_string_value(rec, 'FromUser')
                    buffer = self._db_record_get_blob_value(rec, 'Buffer')
                    deleted = 0 if rec.Deleted == DeletedState.Intact else 1
                    self._parse_user_wc_db_with_value(deleted, node.AbsolutePath, username, buffer)
                except Exception as e:
                    TraceService.Trace(TraceLevel.Debug, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))
        self.im.db_commit()
        self.push_models()
        return True

    def _parse_user_wc_db_with_value(self, deleted, source, username, buffer):
        if buffer is not None and buffer[:8] == 'bplist00':
            try:
                root_mr = MemoryRange.FromBytes(Convert.FromBase64String(base64.b64encode(buffer)))
                root_mr.seek(0)
                root = BPReader.GetTree(root_mr)
            except Exception as e:
                return

            if not root or not root.Children:
                return

            feed = model_wechat.Feed()
            feed.deleted = deleted
            feed.source = source
            feed.account_id = self.user_account.account_id
            feed.sender_id = username
            feed.content = self._bpreader_node_get_string_value(root, 'contentDesc', deleted = deleted)
            feed.timestamp = self._bpreader_node_get_int_value(root, 'createtime', None)

            if 'locationInfo' in root.Children:
                location_node = root.Children['locationInfo']
                latitude = self._bpreader_node_get_float_value(location_node, 'location_latitude')
                longitude = self._bpreader_node_get_float_value(location_node, 'location_longitude')
                if latitude != 0 or longitude != 0:
                    feed.location_latitude = latitude
                    feed.location_longitude = longitude
                    feed.location_type = model_wechat.LOCATION_TYPE_GOOGLE
                    poiName = self._bpreader_node_get_string_value(location_node, 'poiName', deleted = feed.deleted)
                    poiAdress = self._bpreader_node_get_string_value(location_node, 'poiAdress', deleted = feed.deleted)
                    feed.location_address = poiAdress + '' + poiName

            if 'contentObj' in root.Children:
                content_node = root.Children['contentObj']
                moment_type = self._bpreader_node_get_int_value(content_node, 'type')
                media_nodes = []
                if 'mediaList' in content_node.Children and content_node.Children['mediaList'].Values:
                    media_nodes = content_node.Children['mediaList'].Values
                    urls = []
                    for media_node in media_nodes:
                        if 'dataUrl' in media_node.Children:
                            data_node = media_node.Children['dataUrl']
                            if 'url' in data_node.Children:
                                urls.append(data_node.Children['url'].Value)
                    if len(urls) > 0:
                        if moment_type == MOMENT_TYPE_VIDEO:
                            feed.video_path = ','.join(str(u) for u in urls)
                        elif moment_type == MOMENT_TYPE_IMAGE:
                            feed.image_path = ','.join(str(u) for u in urls)
                        elif moment_type == MOMENT_TYPE_SHARED:
                            feed.link_image = urls[0]

                if moment_type in [MOMENT_TYPE_MUSIC, MOMENT_TYPE_SHARED]:
                    feed.link_url = self._bpreader_node_get_string_value(content_node, 'linkUrl', deleted = feed.deleted)
                    feed.link_title = self._bpreader_node_get_string_value(content_node, 'title', deleted = feed.deleted)
                    feed.link_content = self._bpreader_node_get_string_value(content_node, 'desc', deleted = feed.deleted)

            if 'likeUsers' in root.Children:
                for like_node in root.Children['likeUsers'].Values:
                    if canceller.IsCancellationRequested:
                        break
                    try:
                        sender_id = self._bpreader_node_get_string_value(like_node, 'username', deleted = feed.deleted)
                        if sender_id in [None, '']:
                            continue
                        fl = feed.create_like()
                        fl.sender_id = sender_id
                        fl.sender_name = self._bpreader_node_get_string_value(like_node, 'nickname', deleted = feed.deleted)
                        try:
                            fl.timestamp = int(self._bpreader_node_get_int_value(like_node, 'createTime', None))
                        except Exception as e:
                            pass
                        feed.like_count += 1
                    except Exception as e:
                        TraceService.Trace(TraceLevel.Debug, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))
            if feed.like_count == 0:
                feed.like_id = 0

            if 'commentUsers' in root.Children:
                for comment_node in root.Children['commentUsers'].Values:
                    if canceller.IsCancellationRequested:
                        break
                    try:
                        sender_id = self._bpreader_node_get_string_value(comment_node, 'username', deleted = feed.deleted)
                        content = self._bpreader_node_get_string_value(comment_node, 'content', deleted = feed.deleted)
                        if type(sender_id) == str and len(sender_id) > 0 and type(content) == str:
                            fc = feed.create_comment()
                            fc.sender_id = sender_id
                            fc.sender_name = self._bpreader_node_get_string_value(comment_node, 'nickname', deleted = feed.deleted)
                            fc.ref_user_id = self._bpreader_node_get_string_value(comment_node, 'refUserName', deleted = feed.deleted)
                            fc.content = content
                            try:
                                fc.timestamp = int(self._bpreader_node_get_int_value(comment_node, 'createTime', None))
                            except Exception as e:
                                pass
                            feed.comment_count += 1
                    except Exception as e:
                        TraceService.Trace(TraceLevel.Debug, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))
            if feed.comment_count == 0:
                feed.comment_id = 0

            feed.insert_db(self.im)
            model, tl_model = self.get_feed_model(feed)
            self.add_model(model)
            self.add_model(tl_model)

    def _parse_user_fav_db(self, node):
        if node is None:
            return False
        if canceller.IsCancellationRequested:
            return False

        try:
            db = SQLiteParser.Database.FromNode(node, canceller)
        except Exception as e:
            TraceService.Trace(TraceLevel.Error, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))
            return False
        if not db:
            return False

        if 'FavoritesItemTable' in db.Tables:
            ts = SQLiteParser.TableSignature('FavoritesItemTable')
            SQLiteParser.Tools.AddSignatureToTable(ts, "Xml", SQLiteParser.FieldType.Text, SQLiteParser.FieldConstraints.NotNull)
            SQLiteParser.Tools.AddSignatureToTable(ts, "Time", SQLiteParser.FieldType.Int, SQLiteParser.FieldConstraints.NotNull)
            SQLiteParser.Tools.AddSignatureToTable(ts, "SourceType", SQLiteParser.FieldType.Int, SQLiteParser.FieldConstraints.NotNull)
            for rec in db.ReadTableRecords(ts, self.extract_deleted, False, ''):
                if canceller.IsCancellationRequested:
                    break
                if rec is None:
                    continue
                try:
                    local_id = self._db_record_get_int_value(rec, 'LocalId')
                    fav_type = self._db_record_get_int_value(rec, 'Type')
                    timestamp = self._db_record_get_int_value(rec, 'Time')
                    from_user = self._db_record_get_string_value(rec, 'FromUsr')
                    to_user = self._db_record_get_string_value(rec, 'ToUsr')
                    real_name = self._db_record_get_string_value(rec, 'RealChatName')
                    source_type = self._db_record_get_int_value(rec, 'SourceType')
                    xml = self._db_record_get_string_value(rec, 'Xml')
                    deleted = 0 if rec.Deleted == DeletedState.Intact else 1
                    self._parse_user_fav_db_with_value(deleted, node.AbsolutePath, fav_type, timestamp, from_user, xml)
                except Exception as e:
                    TraceService.Trace(TraceLevel.Debug, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))
            self.im.db_commit()
            self.push_models()
        return True

    def _parse_user_fav_db_with_value(self, deleted, source, fav_type, timestamp, from_user, xml):
        favorite = model_wechat.Favorite()
        favorite.source = source
        favorite.deleted = deleted
        favorite.account_id = self.user_account.account_id
        favorite.type = fav_type
        favorite.talker_id = from_user
        if from_user.endswith('@chatroom'):
            favorite.talker_type = model_wechat.CHAT_TYPE_GROUP
        else:
            favorite.talker_type = model_wechat.CHAT_TYPE_FRIEND
        favorite.timestamp = timestamp
        self._parse_user_fav_xml(xml, favorite)
        favorite.insert_db(self.im)
        model = self.get_favorite_model(favorite)
        self.add_model(model)

    def _parse_user_fav_xml(self, xml_str, model):
        xml = None
        try:
            xml = XElement.Parse(xml_str)
        except Exception as e:
            if model.deleted == 0:
                TraceService.Trace(TraceLevel.Debug, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))
        if xml is not None and xml.Name.LocalName == 'favitem':
            try:
                fav_type = int(xml.Attribute('type').Value) if xml.Attribute('type') else 0
            except Exception as e:
                fav_type = 0
            if fav_type == model_wechat.FAV_TYPE_TEXT:
                fav_item = model.create_item()
                fav_item.type = fav_type
                if xml.Element('source'):
                    source_info = xml.Element('source')
                    if source_info.Element('createtime'):
                        try:
                            fav_item.timestamp = int(source_info.Element('createtime').Value)
                        except Exception as e:
                            pass
                    if source_info.Element('realchatname'):
                        fav_item.sender_id = source_info.Element('realchatname').Value
                    elif source_info.Element('fromusr'):
                        fav_item.sender_id = source_info.Element('fromusr').Value
                if xml.Element('desc'):
                    fav_item.content = xml.Element('desc').Value
            elif fav_type in [model_wechat.FAV_TYPE_IMAGE, model_wechat.FAV_TYPE_VOICE, model_wechat.FAV_TYPE_VIDEO, model_wechat.FAV_TYPE_VIDEO_2, model_wechat.FAV_TYPE_ATTACHMENT]:
                fav_item = model.create_item()
                fav_item.type = fav_type
                if xml.Element('source'):
                    source_info = xml.Element('source')
                    if source_info.Element('createtime'):
                        try:
                            fav_item.timestamp = int(source_info.Element('createtime').Value)
                        except Exception as e:
                            pass
                    if source_info.Element('realchatname'):
                        fav_item.sender_id = source_info.Element('realchatname').Value
                    elif source_info.Element('fromusr'):
                        fav_item.sender_id = source_info.Element('fromusr').Value
                if xml.Element('title'):
                    fav_item.content = xml.Element('title').Value
                if xml.Element('datalist') and xml.Element('datalist').Element('dataitem'):
                    ext = 'fav_dat'
                    item = xml.Element('datalist').Element('dataitem')
                    if item.Element('datafmt'):
                        ext = item.Element('datafmt').Value
                    if item.Element('fullmd5'):
                        fav_item.media_path = self._parse_user_fav_path(item.Element('fullmd5').Value, ext)
            elif fav_type == model_wechat.FAV_TYPE_NOTE:
                fav_item = model.create_item()
                fav_item.type = fav_type
                if xml.Element('source') and xml.Element('source').Element('fromusr'):
                    fav_item.sender_id = xml.Element('source').Element('fromusr').Value
                if xml.Element('edittime'):
                    try:
                        fav_item.timestamp = int(xml.Element('edittime').Value)
                    except Exception as e:
                        pass
                if xml.Element('datalist'):
                    for item in xml.Element('datalist').Elements('dataitem'):
                        if item.Attribute('datatype') and item.Attribute('datatype').Value == '1':
                            if item.Element('datadesc'):
                                fav_item.content = item.Element('datadesc').Value
                                break
            elif fav_type == model_wechat.FAV_TYPE_LINK:
                fav_item = model.create_item()
                fav_item.type = fav_type
                if xml.Element('source'):
                    source_info = xml.Element('source')
                    if source_info.Element('createtime'):
                        try:
                            fav_item.timestamp = int(source_info.Element('createtime').Value)
                        except Exception as e:
                            pass
                    if source_info.Element('realchatname'):
                        fav_item.sender_id = source_info.Element('realchatname').Value
                    elif source_info.Element('fromusr'):
                        fav_item.sender_id = source_info.Element('fromusr').Value
                    if source_info.Element('link'):
                        fav_item.link_url = source_info.Element('link').Value
                if xml.Element('weburlitem'):
                    weburlitem = xml.Element('weburlitem')
                    if weburlitem.Element('pagetitle'):
                        fav_item.link_title = weburlitem.Element('pagetitle').Value
                    if weburlitem.Element('pagedesc'):
                        fav_item.link_content = weburlitem.Element('pagedesc').Value
                    if weburlitem.Element('pagethumb_url'):
                        fav_item.link_image = weburlitem.Element('pagethumb_url').Value
                if xml.Element('datalist') and xml.Element('datalist').Element('dataitem'):
                    item = xml.Element('datalist').Element('dataitem')
                    if item.Element('thumbfullmd5') and fav_item.link_image in [None, '']:
                        fav_item.link_image = self._parse_user_fav_path(item.Element('thumbfullmd5').Value, 'fav_thumb')
            elif fav_type == model_wechat.FAV_TYPE_MUSIC:
                fav_item = model.create_item()
                fav_item.type = fav_type
                if xml.Element('source'):
                    source_info = xml.Element('source')
                    if source_info.Element('createtime'):
                        try:
                            fav_item.timestamp = int(source_info.Element('createtime').Value)
                        except Exception as e:
                            pass
                    if source_info.Element('realchatname'):
                        fav_item.sender_id = source_info.Element('realchatname').Value
                    elif source_info.Element('fromusr'):
                        fav_item.sender_id = source_info.Element('fromusr').Value
                if xml.Element('datalist') and xml.Element('datalist').Element('dataitem'):
                    item = xml.Element('datalist').Element('dataitem')
                    if item.Element('datatitle'):
                        fav_item.link_title = item.Element('datatitle').Value
                    if item.Element('datadesc'):
                        fav_item.link_content = item.Element('datadesc').Value
                    if item.Element('stream_weburl'):
                        fav_item.link_url = item.Element('stream_weburl').Value
                    if item.Element('thumbfullmd5'):
                        fav_item.link_image = self._parse_user_fav_path(item.Element('thumbfullmd5').Value, 'fav_thumb')
            elif fav_type == model_wechat.FAV_TYPE_LOCATION:
                fav_item = model.create_item()
                fav_item.type = fav_type
                if xml.Element('source'):
                    source_info = xml.Element('source')
                    if source_info.Element('createtime'):
                        try:
                            fav_item.timestamp = int(source_info.Element('createtime').Value)
                        except Exception as e:
                            pass
                    if source_info.Element('realchatname'):
                        fav_item.sender_id = source_info.Element('realchatname').Value
                    elif source_info.Element('fromusr'):
                        fav_item.sender_id = source_info.Element('fromusr').Value
                if xml.Element('locitem'):
                    latitude = 0
                    longitude = 0
                    locitem = xml.Element('locitem')
                    if locitem.Element('lat'):
                        try:
                            latitude = float(locitem.Element('lat').Value)
                        except Exception as e:
                            pass
                    if locitem.Element('lng'):
                        try:
                            longitude = float(locitem.Element('lng').Value)
                        except Exception as e:
                            pass
                    if latitude != 0 or longitude != 0:
                        fav_item.location_latitude = latitude
                        fav_item.location_longitude = longitude
                        if locitem.Element('label'):
                            fav_item.location_address = locitem.Element('label').Value
                        if locitem.Element('poiname'):
                            fav_item.location_address = locitem.Element('poiname').Value
                        fav_item.location_type = model_wechat.LOCATION_TYPE_GOOGLE
            elif fav_type == model_wechat.FAV_TYPE_CHAT:
                if xml.Element('datalist'):
                    for item in xml.Element('datalist').Elements('dataitem'):
                        fav_item = model.create_item()
                        if item.Attribute('datatype'):
                            try:
                                fav_item.type = int(item.Attribute('datatype').Value)
                            except Exception as e:
                                 pass
                        if item.Element('dataitemsource'):
                            source_info = item.Element('dataitemsource')
                            if source_info.Element('createtime'):
                                try:
                                    fav_item.timestamp = int(source_info.Element('createtime').Value)
                                except Exception as e:
                                    pass
                            if source_info.Element('realchatname'):
                                fav_item.sender_id = source_info.Element('realchatname').Value
                            elif source_info.Element('fromusr'):
                                fav_item.sender_id = source_info.Element('fromusr').Value
                        if fav_item.type == model_wechat.FAV_TYPE_TEXT:
                            if item.Element('datadesc'):
                                fav_item.content = item.Element('datadesc').Value
                        elif fav_item.type in [model_wechat.FAV_TYPE_IMAGE, model_wechat.FAV_TYPE_VOICE, model_wechat.FAV_TYPE_VIDEO, model_wechat.FAV_TYPE_VIDEO_2, model_wechat.FAV_TYPE_ATTACHMENT]:
                            ext = 'fav_dat'
                            if item.Element('datafmt'):
                                ext = item.Element('datafmt').Value
                            if item.Element('fullmd5'):
                                fav_item.media_path = self._parse_user_fav_path(item.Element('fullmd5').Value, ext)
                        elif fav_item.type == model_wechat.FAV_TYPE_LINK:
                            if item.Element('dataitemsource'):
                                source_info = item.Element('dataitemsource')
                                if source_info.Element('link'):
                                    fav_item.link_url = source_info.Element('link').Value
                            if item.Element('weburlitem') and item.Element('weburlitem').Element('pagetitle'):
                                fav_item.link_title = item.Element('weburlitem').Element('pagetitle').Value
                            if item.Element('thumbfullmd5'):
                                fav_item.link_image = self._parse_user_fav_path(item.Element('thumbfullmd5').Value, 'fav_thumb')
                            elif item.Element('weburlitem') and item.Element('weburlitem').Element('pagethumb_url'):
                                fav_item.link_image = item.Element('weburlitem').Element('pagethumb_url').Value
                        elif fav_item.type == model_wechat.FAV_TYPE_MUSIC:
                            if item.Element('datatitle'):
                                fav_item.link_title = item.Element('datatitle').Value
                            if item.Element('datadesc'):
                                fav_item.link_content = item.Element('datadesc').Value
                            if item.Element('stream_weburl'):
                                fav_item.link_url = item.Element('stream_weburl').Value
                            if item.Element('thumbfullmd5'):
                                fav_item.link_image = self._parse_user_fav_path(item.Element('thumbfullmd5').Value, 'fav_thumb')
                        elif fav_item.type == model_wechat.FAV_TYPE_LOCATION:
                            if item.Element('locitem'):
                                latitude = 0
                                longitude = 0
                                locitem = item.Element('locitem')
                                if locitem.Element('lat'):
                                    try:
                                        latitude = float(locitem.Element('lat').Value)
                                    except Exception as e:
                                        pass
                                if locitem.Element('lng'):
                                    try:
                                        longitude = float(locitem.Element('lng').Value)
                                    except Exception as e:
                                        pass
                                if latitude != 0 or longitude != 0:
                                    fav_item.location_type = model_wechat.LOCATION_TYPE_GOOGLE
                                    fav_item.location_latitude = latitude
                                    fav_item.location_longitude = longitude
                                    if locitem.Element('label'):
                                        fav_item.location_address = locitem.Element('label').Value
                                    if locitem.Element('poiname'):
                                        fav_item.location_address = locitem.Element('poiname').Value
                        else:
                            fav_item.content = xml_str
                        if item.Element('datasrcname'):
                            fav_item.sender_name = item.Element('datasrcname').Value
            else:
                fav_item = model.create_item()
                fav_item.type = fav_type
                fav_item.content = xml_str
        return True

    def _parse_user_fav_path(self, filename, ext):
        return self._get_path_from_private_user_node_res('Favorites/Data/{}/{}/{}.{}'.format(filename[:2], filename[-2:], filename, ext))

    def _parse_user_search(self, node):
        if node is None:
            return False
        try:
            node.Data.seek(0)
            content = node.read()
            if content[-2:] == '\x10\x04':
                index = 1
                while index + 5 < len(content):
                    if canceller.IsCancellationRequested:
                        break
                    index += 2
                    size = ord(content[index])
                    index += 1
                    if index + size < len(content):
                        key = content[index:index+size].decode('utf-8')
                        if key is not None and len(key) > 0:
                            search = model_wechat.Search()
                            search.account_id = self.user_account.account_id
                            search.key = key
                            search.source = node.AbsolutePath
                            search.insert_db(self.im)
                            self.add_model(self.get_search_model(search))
                    index += size
                    if content[index:index+2] != '\x10\x04':
                        break
                    index += 2
        except e as Exception:
            pass
        self.im.db_commit()
        self.push_models()

    def _parse_user_fts_db(self, node):
        if node is None:
            return False
        if canceller.IsCancellationRequested:
            return False

        try:
            db = SQLiteParser.Database.FromNode(node, canceller)
        except Exception as e:
            TraceService.Trace(TraceLevel.Error, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))
            return False
        if not db:
            return False

        username_ids = {}
        if 'fts_username_id' in db.Tables:
            ts = SQLiteParser.TableSignature('fts_username_id')
            SQLiteParser.Tools.AddSignatureToTable(ts, "UsrName", SQLiteParser.FieldType.Text, SQLiteParser.FieldConstraints.NotNull)
            SQLiteParser.Tools.AddSignatureToTable(ts, "usernameid", SQLiteParser.FieldType.Int, SQLiteParser.FieldConstraints.NotNull)
            for rec in db.ReadTableRecords(ts, False, False, ''):
                if canceller.IsCancellationRequested:
                    break
                try:
                    username = self._db_record_get_string_value(rec, 'UsrName', '')
                    id = self._db_record_get_int_value(rec, 'usernameid')
                    deleted = 0 if rec.Deleted == DeletedState.Intact else 1
                    if username not in [None, ''] and id != 0:
                        if deleted == 0 or id not in username_ids:
                            username_ids[id] = username
                except Exception as e:
                    TraceService.Trace(TraceLevel.Debug, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))

        tables = [t for t in db.Tables if t.startswith('fts_message_table_') and t.endswith('_content')]
        for table in tables:
            if canceller.IsCancellationRequested:
                break
            ts = SQLiteParser.TableSignature(table)
            for rec in db.ReadTableRecords(ts, False, False, ''):
                if canceller.IsCancellationRequested:
                    break
                if rec is None:
                    continue
                try:
                    usernameid_column = ''
                    message_column = ''
                    for key in rec.Keys:    
                        if key.endswith('usernameid'):
                            usernameid_column = key
                        elif key.endswith('Message'):
                            message_column = key

                    id = self._db_record_get_int_value(rec, usernameid_column, 0)
                    content = self._db_record_get_string_value(rec, message_column, '')
                    if (id not in username_ids) or content == '':
                        continue
                    username = username_ids.get(id)
                    #deleted = 0 if rec.Deleted == DeletedState.Intact else 1
                    self._parse_user_fts_db_with_value(1, node.AbsolutePath, username, content)
                except Exception as e:
                    TraceService.Trace(TraceLevel.Debug, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))
            self.im.db_commit()
            self.push_models()
        return True

    def _parse_user_fts_db_with_value(self, deleted, source, username, content): 
        message = model_wechat.Message()
        message.deleted = deleted
        message.source = source
        message.account_id = self.user_account.account_id
        message.talker_id = username
        message.content = content
        if username.endswith('@chatroom'):
            message.talker_type = model_wechat.CHAT_TYPE_GROUP
        else:
            message.talker_type = model_wechat.CHAT_TYPE_FRIEND
        message.insert_db(self.im)
        model, tl_model = self.get_message_model(message)
        self.add_model(model)
        self.add_model(tl_model)

    @staticmethod
    def _process_parse_contact_remark(blob):
        nickname = ''
        alias = ''
        remark = ''

        try:
            index = 0
            while index + 2 < len(blob):
                flag = ord(blob[index])
                size = ord(blob[index + 1])
                if index + 2 + size > len(blob):
                    break
                content = blob[index + 2: index + 2 + size].decode('utf-8')
                if flag == 0x0a:  # nickname
                    nickname = content
                elif flag == 0x12:  # alias
                    alias = content
                elif flag == 0x1a:  # remark
                    remark = content
                index += 2 + size
        except Exception as e:
            pass
        return nickname, alias, remark

    @staticmethod
    def _process_parse_contact_profile(blob):
        gender = model_wechat.GENDER_NONE
        country = ''
        province = ''
        city = ''
        signature = ''

        try:
            index = 0
            while index + 2 < len(blob):
                flag = ord(blob[index])
                if flag == 0x08:
                    gender = ord(blob[index + 1])
                    index += 2
                else:
                    size = ord(blob[index + 1])
                    if size > 0:
                        content = blob[index + 2: index + 2 + size].decode('utf-8')
                        if flag == 0x12:  # country
                            country = content
                        elif flag == 0x1a:  # province
                            province = content
                        elif flag == 0x22:  # city
                            city = content
                        elif flag == 0x2a:  # signature
                            signature = content
                    index += 2 + size
        except Exception as e:
            pass
        region = country
        if len(province) > 0:
            region += ' ' + province
        if len(city) > 0:
            region += ' ' + city
        return gender, region, signature

    @staticmethod
    def _process_parse_contact_head(blob):
        head = None
        head_hd = None

        try:
            index = 2
            while index + 1 < len(blob):
                flag = ord(blob[index])
                size = ord(blob[index + 1])
                if size > 0:
                    index += 2
                    if ord(blob[index]) != 0x68:
                        index += 1
                    if index + size > len(blob):
                        break

                    content = blob[index: index + size].decode('utf-8')
                    if flag == 0x12:
                        head = content
                    elif flag == 0x1a:
                        head_hd = content

                    index += size
                else:
                    index += 2
        except Exception as e:
            pass

        return head, head_hd

    @staticmethod
    def _process_parse_group_members(blob, deleted):
        members = []
        max_count = 0

        prefix = b'<RoomData>'
        suffix = b'</RoomData>'
        if blob is not None and prefix in blob and suffix in blob:
            ms = []
            try:
                index_begin = blob.index(prefix)
                index_end = blob.index(suffix) + len(suffix)
                content = blob[index_begin:index_end].decode('utf-8')
                xml = XElement.Parse(content)
                if xml.Element('MaxCount'):
                    max_count = int(xml.Element('MaxCount').Value)
                ms = Enumerable.ToList[XElement](XPathExtensions.XPathSelectElements(xml,"Member[@UserName]"))
            except Exception as e:
                if deleted == 0:
                    TraceService.Trace(TraceLevel.Debug, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))
            for m in ms:
                if canceller.IsCancellationRequested:
                    break
                username = None
                display_name = None
                if m.Attribute('UserName'):
                    username = m.Attribute('UserName').Value
                if m.Element("DisplayName"):
                    display_name = m.Element("DisplayName").Value
                if username is not None:
                    members.append({'username': username, 'display_name': display_name})
        return members, max_count

    def _process_parse_friend_message(self, msg, msg_type, msg_local_id, friend_hash, model):
        content = msg
        img_path = None
        img_thum_path = None
        revoke_content = None

        seps = [':\n', '*#*\n']
        for sep in seps:
            index = msg.find(sep)
            if index != -1:
                content = msg[index+len(sep):]
                break

        if msg_type == MSG_TYPE_TEXT:
            pass
        elif msg_type == MSG_TYPE_IMAGE:
            content = '[图片]'
            img_path = self._get_path_from_user_node_res('Img/{0}/{1}.pic_hd'.format(friend_hash, msg_local_id))
            if img_path is None:
                img_path = self._get_path_from_user_node_res('Img/{0}/{1}.pic'.format(friend_hash, msg_local_id))
            
            img_thum_path = self._get_path_from_user_node_res('Img/{0}/{1}.pic_thum'.format(friend_hash, msg_local_id))
        elif msg_type == MSG_TYPE_VOICE:
            content = '[语音]'
            img_path = self._get_path_from_user_node_res('Audio/{0}/{1}.aud'.format(friend_hash, msg_local_id))
        elif msg_type in [MSG_TYPE_VIDEO, MSG_TYPE_VIDEO_2]:
            content = '[视频]'
            img_path = self._get_path_from_user_node_res('Video/{0}/{1}.mp4'.format(friend_hash, msg_local_id))
            img_thum_path = self._get_path_from_user_node_res('Video/{0}/{1}.video_thum'.format(friend_hash, msg_local_id))
        elif msg_type == MSG_TYPE_LOCATION:
            content = self._process_parse_message_location(content, model)
            img_thum_path = self._get_path_from_user_node_res('Location/{0}/{1}.pic_thum'.format(friend_hash, msg_local_id))
        elif msg_type == MSG_TYPE_EMOJI:
            self._process_parse_message_emoji(content, model)
            content = '[表情]'
        elif msg_type == MSG_TYPE_CONTACT_CARD:
            content = self._process_parse_message_contact_card(content, model)
        elif msg_type == MSG_TYPE_VOIP:
            content = self._process_parse_message_voip(content)
        elif msg_type == MSG_TYPE_VOIP_GROUP:
            content = self._process_parse_message_voip_group(content)
        elif msg_type == MSG_TYPE_SYSTEM:
            pass
        elif msg_type in [MSG_TYPE_SYSTEM_2, MSG_TYPE_SYSTEM_3]:
            content, revoke_content = self._process_parse_message_system_xml(content)
        elif msg_type == MSG_TYPE_LINK_SEMI:
            pass
        else:  # MSG_TYPE_LINK
            content = self._process_parse_message_link(content, model, msg_local_id, friend_hash)

        model.content = content
        model.media_path = img_path
        model.media_thum_path = img_thum_path
        return revoke_content

    def _process_parse_group_message(self, msg, msg_type, msg_local_id, is_sender, group_hash, model):
        sender_id = self.user_account.account_id
        content = msg

        if not is_sender:
            seps = [':\n', '*#*\n']
            for sep in seps:
                index = msg.find(sep)
                if index != -1:
                    sender_id = msg[:index]
                    content = msg[index+len(sep):]
                    break

        model.sender_id = sender_id
        return self._process_parse_friend_message(content, msg_type, msg_local_id, group_hash, model)

    def _process_parse_message_emoji(self, xml_str, model):
        model.media_path = None
        xml = None
        try:
            xml = XElement.Parse(xml_str)
        except Exception as e:
            if model.deleted == 0:
                TraceService.Trace(TraceLevel.Debug, "apple_wechat.py Error: LINE {} \nxml: {}".format(traceback.format_exc(), xml_str))
        if xml and xml.Element('emoji'):
            emoji = xml.Element('emoji')
            if emoji.Attribute('fromusername') and model.sender_id in [None, '']:
                model.sender_id = emoji.Attribute('fromusername').Value
            if emoji.Attribute('md5') and self.private_user_node:
                hash = emoji.Attribute('md5').Value
                model.media_path = self._get_path_from_private_user_node_res('emoticonPIC/{}.pic'.format(hash))
                if model.media_path is None:
                    model.media_path = self._get_path_from_private_user_node_res('emoticonThumb/{}.pic'.format(hash))
            if model.media_path is None and emoji.Attribute('cdnurl'):
                 model.media_path = emoji.Attribute('cdnurl').Value

    def _process_parse_message_link(self, xml_str, model, msg_local_id, friend_hash):
        content = xml_str
        xml = None
        try:
            xml_content = xml_str.replace('\b', '')  # remove '\b' char
            index = xml_content.find('<?xml version="1.0"?>')
            if index > 0:
                xml_content = xml_content.replace('<?xml version="1.0"?>', '')  # remove xml declare not in front of content
            xml = XElement.Parse(xml_content)
        except Exception as e:
            if model.deleted == 0:
                TraceService.Trace(TraceLevel.Debug, "apple_wechat.py Error: LINE {} \nxml: {}".format(traceback.format_exc(), xml_str))
            model.type = model_wechat.MESSAGE_CONTENT_TYPE_TEXT
            return

        if xml is not None:
            if xml.Name.LocalName == 'msg':
                appmsg = xml.Element('appmsg')
                if appmsg is not None:
                    try:
                        msg_type = int(appmsg.Element('type').Value) if appmsg.Element('type') else 0
                    except Exception as e:
                        msg_type = 0
                    if msg_type in [2000, 2001]:  # 红包转账收款
                        self._process_parse_message_deal(xml, model)
                        content = ''
                    elif msg_type == 6:  # 附件
                        content = ''
                        model.type = model_wechat.MESSAGE_CONTENT_TYPE_ATTACHMENT
                        if appmsg.Element('title'):
                            content = appmsg.Element('title').Value
                        if appmsg.Element('des'):
                            model.link_content = appmsg.Element('des').Value
                        ext = ''
                        if appmsg.Element('appattach') and appmsg.Element('appattach').Element('fileext'):
                            ext = appmsg.Element('appattach').Element('fileext').Value
                        if ext == '':
                            ext = 'dat'
                        model.media_path = self._get_path_from_user_node_res('OpenData/{}/{}.{}'.format(friend_hash, msg_local_id, ext))
                    elif msg_type == 9:  # 提醒
                        if appmsg.Element('des'):
                            content = appmsg.Element('des').Value
                            model.type = model_wechat.MESSAGE_CONTENT_TYPE_TEXT
                    elif msg_type == 17:  # 位置共享
                        if appmsg.Element('title'):
                            content = appmsg.Element('title').Value
                            model.type = model_wechat.MESSAGE_CONTENT_TYPE_TEXT
                    else:
                        mmreader = appmsg.Element('mmreader')
                        if mmreader and mmreader.Element('category'):
                            content = ''
                            count = 1
                            if mmreader.Element('category').Attribute('count'):
                                count = int(mmreader.Element('category').Attribute('count').Value)
                            if count > 1:
                                items = mmreader.Element('category').Elements('item')
                                contents = []
                                for item in items:
                                    info = {}
                                    if item.Element('title'):
                                        info['title'] = item.Element('title').Value
                                    if item.Element('digest'):
                                        info['description'] = item.Element('digest').Value
                                    if item.Element('url'):
                                        info['url'] = item.Element('url').Value
                                    if item.Element('cover'):
                                        info['image'] = item.Element('cover').Value
                                    if len(info) > 0:
                                        contents.append(info)
                                try:
                                    content = json.dumps(contents, ensure_ascii=False)
                                    model.type = model_wechat.MESSAGE_CONTENT_TYPE_LINK_SET
                                except Exception as e:
                                    item = mmreader.Element('category').Element('item')
                                    if item is not None:
                                        if item.Element('title'):
                                            model.link_title = item.Element('title').Value
                                        if item.Element('digest'):
                                            model.link_content = item.Element('digest').Value
                                        if item.Element('url'):
                                            model.link_url = item.Element('url').Value
                                        if item.Element('cover'):
                                            model.link_image = item.Element('cover').Value
                            elif count == 1:
                                item = mmreader.Element('category').Element('item')
                                if item is not None:
                                    if item.Element('title'):
                                        model.link_title = item.Element('title').Value
                                    if item.Element('digest'):
                                        model.link_content = item.Element('digest').Value
                                    if item.Element('url'):
                                        model.link_url = item.Element('url').Value
                                    if item.Element('cover'):
                                        model.link_image = item.Element('cover').Value
                        else:
                            content = ''
                            if appmsg.Element('title'):
                                model.link_title = appmsg.Element('title').Value
                            if appmsg.Element('des'):
                                model.link_content = appmsg.Element('des').Value
                            if appmsg.Element('url'):
                                model.link_url = appmsg.Element('url').Value
                            appinfo = xml.Element('appinfo')
                            if appinfo and appinfo.Element('appname'):
                                model.link_from = appinfo.Element('appname').Value
                            model.link_image = self._get_path_from_user_node_res('OpenData/{}/{}.pic_thum'.format(friend_hash, msg_local_id))
                            if model.link_image is None and appmsg.Element('thumburl'):
                                model.link_image = appmsg.Element('thumburl').Value
                else:
                    pass
            elif xml.Name.LocalName == 'mmreader':
                category = xml.Element('category')
                if category and category.Element('item'):
                    content = ''
                    item = category.Element('item')
                    if item.Element('title'):
                        model.link_title = item.Element('title').Value
                    if item.Element('digest'):
                        model.link_content = item.Element('digest').Value
                    if item.Element('url'):
                        model.link_url = item.Element('url').Value
                    if item.Element('cover'):
                        model.link_image = item.Element('cover').Value
            elif xml.Name.LocalName == 'appmsg':
                content = ''
                if xml.Element('title'):
                    model.link_title = xml.Element('title').Value
                if xml.Element('des'):
                    model.link_content = xml.Element('des').Value
                if xml.Element('url'):
                    model.link_url = xml.Element('url').Value
                appinfo = xml.Element('appinfo')
                if appinfo and appinfo.Element('appname'):
                    model.link_from = appinfo.Element('appname').Value
                model.link_image = self._get_path_from_user_node_res('OpenData/{}/{}.pic_thum'.format(friend_hash, msg_local_id))
                if model.link_image is None and appmsg.Element('thumburl'):
                    model.link_image = appmsg.Element('thumburl').Value
            else:
                pass
        return content

    def _process_parse_message_tencent_news(self, xml_str, model):
        content = xml_str
        news = []
        xml = None
        try:
            xml = XElement.Parse(xml_str)
        except Exception as e:
            model.type = model_wechat.MESSAGE_CONTENT_TYPE_TEXT
        if xml and xml.Name.LocalName == 'mmreader' and xml.Element('category'):
            contents = []
            items = xml.Element('category').Elements('newitem')
            for item in items:
                info = {}
                if item.Element('title'):
                    info['title'] = item.Element('title').Value
                if item.Element('digest'):
                    info['description'] = item.Element('digest').Value
                if item.Element('url'):
                    info['url'] = item.Element('url').Value
                if item.Element('cover'):
                    info['image'] = item.Element('cover').Value
                if len(info) > 0:
                    contents.append(info)
            try:
                content = json.dumps(contents, ensure_ascii=False)
                model.type = model_wechat.MESSAGE_CONTENT_TYPE_LINK_SET
            except Exception as e:
                item = xml.Element('category').Element('newitem')
                if item is not None:
                    model.type = model_wechat.MESSAGE_CONTENT_TYPE_LINK
                    content = ''
                    if item.Element('title'):
                        model.link_title = item.Element('title').Value
                    if item.Element('digest'):
                        model.link_content = item.Element('digest').Value
                    if item.Element('url'):
                        model.link_url = item.Element('url').Value
                    if item.Element('cover'):
                        model.link_image = item.Element('cover').Value
                else:
                    model.type = model_wechat.MESSAGE_CONTENT_TYPE_TEXT
        return content

    def _parse_pay_card(self):
        node = self.user_node.GetByPath('WCPay/WCPayPayCardList.list')
        if node is None:
            return False

        root = None
        try:
            root = BPReader.GetTree(node)
        except Exception as e:
            return False
        if not root or not root.Value:
            return False

        for card_node in root.Value:
            if 'm_cardNumber' in card_node.Children:
                card_number = self._bpreader_node_get_string_value(card_node, 'm_cardNumber')
                if card_number not in [None, '', 'None']:
                    card = model_wechat.BankCard()
                    card.source = node.AbsolutePath
                    card.account_id = self.user_account.account_id
                    card.card_number = card_number
                    card.bank_name = self._bpreader_node_get_string_value(card_node, 'm_cardBankName')
                    card.card_type = self._bpreader_node_get_string_value(card_node, 'm_cardTypeName')
                    card.insert_db(self.im)
                    self.add_model(self.get_bank_card_model(card))
        self.im.db_commit()
        self.push_models()
        return True

    def _parse_user_story_db(self, node):
        if node is None:
            return False
        if canceller.IsCancellationRequested:
            return False
        try:
            db = SQLiteParser.Database.FromNode(node, canceller)
        except Exception as e:
            TraceService.Trace(TraceLevel.Error, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))
            return False
        if not db:
            return False

        if 'WCStoryTable' in db.Tables:
            ts = SQLiteParser.TableSignature('WCStoryTable')
            SQLiteParser.Tools.AddSignatureToTable(ts, "username", SQLiteParser.FieldType.Text, SQLiteParser.FieldConstraints.NotNull)
            SQLiteParser.Tools.AddSignatureToTable(ts, "tid", SQLiteParser.FieldType.Text, SQLiteParser.FieldConstraints.NotNull)
            SQLiteParser.Tools.AddSignatureToTable(ts, "mediaItem", SQLiteParser.FieldType.Blob)
            SQLiteParser.Tools.AddSignatureToTable(ts, "commentList", SQLiteParser.FieldType.Blob)
            SQLiteParser.Tools.AddSignatureToTable(ts, "createtime", SQLiteParser.FieldType.Int, SQLiteParser.FieldConstraints.NotNull)
            for rec in db.ReadTableRecords(ts, self.extract_deleted, False, ''):
                if canceller.IsCancellationRequested:
                    break
                if rec is None:
                    continue
                try:
                    username = self._db_record_get_string_value(rec, 'username')
                    if username in [None, '']:
                        continue
                    tid = self._db_record_get_string_value(rec, 'tid')
                    media_item = self._db_record_get_blob_value(rec, 'mediaItem')
                    comment_list = self._db_record_get_blob_value(rec, 'commentList')
                    local_info = self._db_record_get_blob_value(rec, 'localInfoData')
                    timestamp = self._db_record_get_int_value(rec, 'createtime')
                    
                    deleted = 0 if rec.Deleted == DeletedState.Intact else 1
                    self._parse_user_story_db_with_value(deleted, node.AbsolutePath, username, tid, media_item, comment_list, local_info, timestamp)
                except Exception as e:
                    TraceService.Trace(TraceLevel.Debug, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))
            self.im.db_commit()
            self.push_models()
        return True

    def _parse_user_story_db_with_value(self, deleted, source, username, tid, media_item, comment_list, local_info, timestamp):
        media_path = self._parse_user_story_media_local_path(tid)
        if media_path is None:
            media_path = self._parse_user_story_media_network_path(media_item)
        comments = self._parse_user_story_comments(comment_list)

        story = model_wechat.Story()
        story.account_id = self.user_account.account_id
        story.sender_id = username
        story.media_path = media_path
        story.timestamp = timestamp

    def _parse_user_story_media_local_path(self, tid):
        if self.private_user_node:
            name = self._md5(tid)
            node = self.private_user_node.GetByPath('/story/media_data/{}/{}.mp4'.format(name[:2], name[2:]))
        return None

    def _parse_user_story_media_network_path(self, media_item):
        return None

    def _parse_user_story_comments(self, comment_list):
        return []

    def _parse_user_app_db(self, node):
        if node is None:
            return False
        if canceller.IsCancellationRequested:
            return False
        try:
            db = SQLiteParser.Database.FromNode(node, canceller)
        except Exception as e:
            TraceService.Trace(TraceLevel.Error, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))
            return False
        if not db:
            return False

        if 'WeAppContactTable' in db.Tables:
            ts = SQLiteParser.TableSignature('WeAppContactTable')
            for rec in db.ReadTableRecords(ts, self.extract_deleted, False, ''):
                if canceller.IsCancellationRequested:
                    break
                if rec is None:
                    continue
                try:
                    username = self._db_record_get_string_value(rec, 'userName')
                    if username in [None, '']:
                        continue
                    head = self._db_record_get_string_value(rec, 'brandIconURL')
                    contact_pack = self._db_record_get_blob_value(rec, 'contactPack')
                    
                    deleted = 0 if rec.Deleted == DeletedState.Intact else 1
                    self._parse_user_app_db_with_value(deleted, node.AbsolutePath, username, head, contact_pack)
                except Exception as e:
                    TraceService.Trace(TraceLevel.Debug, "apple_wechat.py Error: LINE {}".format(traceback.format_exc()))
            self.im.db_commit()
            self.push_models()
        return True

    def _parse_user_app_db_with_value(self, deleted, source, username, head, contact_pack):
        nickname = self._process_parse_app_contact_pack(contact_pack)

        friend = model_wechat.Friend()
        friend.deleted = deleted
        friend.source = source
        friend.account_id = self.user_account.account_id
        friend.friend_id = username
        friend.nickname = nickname
        friend.type = model_wechat.FRIEND_TYPE_PROGRAM
        friend.photo = head
        friend.insert_db(self.im)
        model = self.get_friend_model(friend)
        self.add_model(model)

    @staticmethod
    def _process_parse_app_contact_pack(blob):
        nickname = ''
        try:
            index = 0
            while index + 2 < len(blob):
                flag = ord(blob[index])
                size = ord(blob[index + 1])
                if index + 2 + size > len(blob):
                    break
                content = blob[index + 2: index + 2 + size].decode('utf-8')
                if flag == 0x12:  # nickname
                    nickname = content
                index += 2 + size
        except Exception as e:
            pass
        return nickname

    def _generate_user_node_res(self):
        self.user_node_res = set()
        self.user_node_absolute_path = None
        if self.user_node is not None:
            self.user_node_absolute_path = self.user_node.AbsolutePath
            conditions = ['Img/.+/.+\.pic_hd$', 'Img/.+/.+\.pic$', 'Img/.+/.+\.pic_thumb$', 
                          'Audio/.+/.+\.aud$', 'Video/.+/.+\.mp4', 'Video/.+/.+\.video_thum', 
                          'Location/.+/.+\.pic_thumb$', 'OpenData/.+/.+\..+$']
            idx = len(self.user_node_absolute_path) + 1
            for c in conditions:
                rs = self.user_node.Search(c)
                for r in rs:
                    self.user_node_res.add(r.AbsolutePath[idx:])

        self.private_user_node_res = set()
        self.private_user_node_absolute_path = None
        if self.private_user_node is not None:
            self.private_user_node_absolute_path = self.private_user_node.AbsolutePath
            conditions = ['Favorites/Data/.+/.+/.+\..+$', 'emoticonPIC/.+\.pic$', 'emoticonThumb/.+\.pic$', 
                          'HeadImg/0/.+/.+\.pic_hd$', 'HeadImg/0/.+/.+\.pic_compressed']
            idx = len(self.private_user_node.AbsolutePath) + 1
            for c in conditions:
                rs = self.private_user_node.Search(c)
                for r in rs:
                    self.private_user_node_res.add(r.AbsolutePath[idx:])

    def _clear_user_node_res(self):
        self.user_node_res.clear()
        self.private_user_node_res.clear()

    def _get_path_from_user_node_res(self, path):
        if path in self.user_node_res:
            return self.user_node_absolute_path + '/' + path
        else:
            return None

    def _get_path_from_private_user_node_res(self, path):
        if path in self.private_user_node_res:
            return self.private_user_node_absolute_path + '/' + path
        else:
            return None
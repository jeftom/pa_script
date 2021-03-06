﻿# coding=utf-8
__author__ = 'YangLiyuan'

import clr

try:
    clr.AddReference('model_sim')
    clr.AddReference('bcp_basic')
    clr.AddReference('ScriptUtils')
except:
    pass
del clr

import bcp_basic
import model_sim
from ScriptUtils import DEBUG, CASE_NAME, exc, tp, base_analyze, parse_decorator, BaseParser

# app数据库版本
VERSION_APP_VALUE = 3


@parse_decorator
def analyze_sim(node, extract_deleted, extract_source):
    """
        android 小米 SIM (user_de/0/com.android.providers.telephony/databases/telephony.db)
        user_de/0/com.android.providers.telephony/databases$
    """
    node_path = node.AbsolutePath
    tp(node.AbsolutePath)
    _Parser = SIMParser

    if node_path.endswith('sim/sim.db'):
        _Parser = SIMParser_no_tar
    elif node_path.endswith('com.android.providers.telephony/databases/telephony.db'):
        _Parser = SIMParser
    elif node_path.endswith('simcardmanagement.db'):
        _Parser = OldSamsungSIMParser

    return base_analyze(_Parser,
                        node,
                        bcp_basic.BASIC_SIM_INFORMATION,
                        VERSION_APP_VALUE,
                        build_name='SIM 卡',
                        db_name='AndroidSIM')


class SIMParser(BaseParser):
    """ \user_de\0\com.android.providers.telephony\databases\telephony.db """

    def __init__(self, node, db_name):
        super(SIMParser, self).__init__(node, db_name)
        self.root = node.Parent
        self.VERSION_VALUE_DB = model_sim.VERSION_VALUE_DB
        self.csm = model_sim.Model_SIM()
        self.Generate = model_sim.GenerateModel

    def parse_main(self):
        node = self.root.GetByPath("/telephony.db")
        if not self._read_db(node=node):
            return []
        self.parse_siminfo()

    def parse_siminfo(self):
        """ telephony.db - siminfo

            RecNo	FieldName	SQLType	Size	 
            1	_id	                INTEGER
            2	icc_id	                TEXT
            3	sim_id	                INTEGER			
            4	display_name	        TEXT
            5	carrier_name	        TEXT
            6	name_source	            INTEGER
            7	color	                INTEGER
            8	number	                TEXT
            9	display_number_format	INTEGER
            10	data_roaming	                INTEGER
            11	mcc	                INTEGER
            12	mnc	                INTEGER
        """
        for rec in self._read_table(table_name='siminfo'):
            if self._is_empty(rec, 'sim_id', 'display_name'):
                continue
            try:
                sim = model_sim.SIM()
                sim.name    = rec['display_name'].Value.replace('CMCC', '中国移动')
                sim.msisdn  = rec['number'].Value
                sim.iccid   = rec['icc_id'].Value
                sim.source  = self.cur_db_source
                sim.deleted = 1 if rec.IsDeleted else 0
                self.csm.db_insert_table_sim(sim)
            except:
                exc()
        self.csm.db_commit()


class SIMParser_no_tar(SIMParser):
    ''' 处理没有 tar 包的案例 '''

    def __init__(self, node, db_name):
        super(SIMParser_no_tar, self).__init__(node, db_name)
        self.root = node

    def parse_main(self):
        if not self._read_db(node=self.root):
            return
        self.parse_sim()

    def parse_sim(self):
        ''' sim/sim.db - SIM
        RecNo	FieldName	SQLType	
        1	displayName	TEXT		
        2	phoneNumber	TEXT		
        '''
        for rec in self._read_table(table_name='SIM', read_delete=False):
            if self._is_empty(rec, 'displayName'):
                continue
            try:
                sim = model_sim.SIM()
                sim.name   = rec['displayName'].Value
                sim.msisdn = rec['phoneNumber'].Value
                sim.source = self.cur_db_source
                self.csm.db_insert_table_sim(sim)
            except:
                exc()
        try:
            self.csm.db_commit()
        except:
            exc()


class OldSamsungSIMParser(SIMParser):
    ''' com.android.simcardmanagement/databases/simcardmanagement.db - registerinfo'''

    def __init__(self, node, db_name):
        super(OldSamsungSIMParser, self).__init__(node, db_name)
        self.root = node

    def parse_main(self):
        if not self._read_db(node=self.root):
            return
        self.parse_simcardmanagement()

    def parse_simcardmanagement(self):
        ''' simcardmanagement.db - registerinfo

            FieldName	    SQLType
            _id	            INTEGER     PK
            card_id	        VARCHAR
            card_iccid	    VARCHAR
            card_type	    VARCHAR
            card_name	    VARCHAR
            card_number	    VARCHAR
            slot_number	    INTEGER
            icon_index	    INTEGER
            icon_name	    VARCHAR
        '''
        for rec in self._read_table('registerinfo', read_delete=False):
            if (self._is_empty(rec, 'card_iccid')
                    or self._is_duplicate(rec, '_id')):
                continue
            try:
                sim = model_sim.SIM()
                sim.name = rec['card_name'].Value
                sim.iccid = rec['card_iccid'].Value
                if rec['card_number'].Value != 'UNKNOWN':
                    sim.msisdn = rec['card_number'].Value
                sim.source = self.cur_db_source
                self.csm.db_insert_table_sim(sim)
            except:
                exc()
        self.csm.db_commit()

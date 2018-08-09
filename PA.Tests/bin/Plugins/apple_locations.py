#coding=utf-8
import os
import PA_runtime
from PA_runtime import *

class LocationsParser(object):

    VALID_MAC_RE = re.compile('^(?:[0-9A-F]{1,2}:){5}[0-9A-F]{1,2}$', re.IGNORECASE)

    def __init__(self, node, extract_deleted, extract_source):
        self.db = SQLiteParser.Tools.GetDatabaseByPath(node, '')
        self.extract_deleted = extract_deleted
        self.extract_source = extract_source
        self.ds = node.FileSystem.DataStore

    @staticmethod
    def normalize_mac(mac):
        temp_mac = mac.split(':')
        mac = ''
        for b in temp_mac:
            if len(b) == 1:
                mac += '0{0}:'.format(b)
            elif len(b) == 2:
                mac += '{0}:'.format(b)
        return mac[:-1].upper()

    def validate_coordinate(self, record):
        if IsDBNull(record['Longitude'].Value) or IsDBNull(record['Latitude'].Value):
            return False
        return \
            record['Longitude'].Value != 0 and \
            record['Latitude'].Value != 0 and \
            abs(record['Longitude'].Value) < 180 and \
            abs(record['Latitude'].Value) < 90

    def get_coordinate(self, record):
        c = Coordinate()
        c.Deleted = record.Deleted
        try:
            SQLiteParser.Tools.ReadColumnToField[float](record, 'Longitude', c.Longitude, self.extract_source, lambda x: float(x))
            SQLiteParser.Tools.ReadColumnToField[float](record, 'Latitude', c.Latitude, self.extract_source, lambda x: float(x))
        except:
            return None
        return c

    def get_timestamp_from_record(self, record, ts_field):
        if not IsDBNull(record['Timestamp'].Value):
            try:
                timestamp = TimeStamp(TimeStampFormats.GetTimeStampEpoch1Jan2001(record['Timestamp'].Value), True)
            except:
                return
            if timestamp.Value.Year < 2006:
                return
            ts_field.Value = timestamp
            if self.extract_source:
                ts_field.Source = MemoryRange(record['Timestamp'].Source)

    def get_description_from_record(self, record, desc_field, desc_cols):
        desc = []
        desc_source = []
        for name in desc_cols:
            if name not in record:
                continue
            value = record[name].Value
            if value != -1:
                desc.append('{0}={1}'.format(name, value))
                if self.extract_source:
                    desc_source.extend(record[name].Source)

            desc_field.Value = " ".join(desc)
            if self.extract_source:
                desc_field.Source = MemoryRange(desc_source)

    def get_mac_from_record(self, record, field):
        if not IsDBNull(record['MAC'].Value):
            mac = record['MAC'].Value
            if self.VALID_MAC_RE.match(mac) is None:
                return
            field.Value = self.normalize_mac(mac)
            if self.extract_source:
                field.Source = MemoryRange(record['MAC'].Source)

    def get_coordinate_and_data_from_record(self, record, result):
        cor = self.get_coordinate(record)
        if cor is not None:
            result.Position.Value = self.get_coordinate(record)
        SQLiteParser.Tools.ReadColumnToField[str](record, 'Confidence', result.Confidence, self.extract_source,
                                                  lambda x: str(x))
        SQLiteParser.Tools.ReadColumnToField[str](record, 'HorizontalAccuracy', result.Precision,
                                                  self.extract_source, lambda x: str(x))

    def parse_cell_locations(self):
        if self.db is None or 'CellLocation' not in self.db.Tables:
            return []
        ts = SQLiteParser.TableSignature('CellLocation')
        if self.extract_deleted:
            ts['Latitude'] = ts['Longitude'] = ts['Timestamp'] = SQLiteParser.Signatures.NumericSet(7)
            ts['Confidence'] = SQLiteParser.Signatures.NumericSet(1)
            ts['HorizontalAccuracy'] = SQLiteParser.Signatures.SignatureFactory.GetFieldSignature(SQLiteParser.FieldType.Int)
            ts['MCC'] = ts['MNC'] = SQLiteParser.Signatures.NumericRange(1, 2)
            ts['LAC'] = SQLiteParser.Signatures.NumericRange(1, 3)
            ts['CI'] = SQLiteParser.Signatures.NumericRange(1, 4)

        results = []
        for record in self.db.ReadTableRecords(ts, self.extract_deleted, True):
            if not self.validate_coordinate(record):
                continue

            result = Location()
            result.Deleted = record.Deleted
            result.Category.Value = LocationCategories.CELL_TOWERS

            cell = CellTower()
            cell.Deleted = result.Deleted

            SQLiteParser.Tools.ReadColumnToField[str](record, 'MCC', cell.MCC, self.extract_source, str)
            SQLiteParser.Tools.ReadColumnToField[str](record, 'MNC', cell.MNC, self.extract_source, str)
            SQLiteParser.Tools.ReadColumnToField[str](record, 'LAC', cell.LAC, self.extract_source, str)
            if record.ContainsKey("CI") and not IsDBNull(record["CI"].Value) and record["CI"].Value >= 0:
                SQLiteParser.Tools.ReadColumnToField[str](record, 'CI', cell.CID, self.extract_source, str)

            self.get_timestamp_from_record(record, result.TimeStamp)
            cell.TimeStamp.Init(result.TimeStamp)
            self.get_description_from_record(record, result.Description, ['MCC', 'MNC', 'LAC', 'CI'])
            self.get_coordinate_and_data_from_record(record, result)
            cell.Position.Value = result.Position.Value
            results.append(result)
            if cell.HasLogicalContent:
                results.append(cell)
        return results

    def parse_cdma_cell_location(self):
        if self.db is None or 'CdmaCellLocation' not in self.db.Tables:
            return []

        ts = SQLiteParser.TableSignature('CdmaCellLocation')
        if self.extract_deleted:
            ts['Latitude'] = ts['Longitude'] = ts['Timestamp'] = SQLiteParser.Signatures.NumericSet(7)
            ts['Confidence'] = SQLiteParser.Signatures.NumericSet(1)
            ts['HorizontalAccuracy'] = SQLiteParser.Signatures.SignatureFactory.GetFieldSignature(SQLiteParser.FieldType.Int)
            ts['MCC'] = ts['SID'] = ts['NID'] = ts['BSID'] = SQLiteParser.Signatures.NumericRange(1, 2)

        results = []
        for record in self.db.ReadTableRecords(ts, self.extract_deleted, True):
            if not self.validate_coordinate(record):
                continue

            result = Location()
            result.Deleted = record.Deleted
            result.Category.Value = LocationCategories.CELL_TOWERS

            cell = CellTower()
            cell.Deleted = result.Deleted

            SQLiteParser.Tools.ReadColumnToField[str](record, 'MCC', cell.MCC, self.extract_source, str)
            SQLiteParser.Tools.ReadColumnToField[str](record, 'SID', cell.SID, self.extract_source, str)
            SQLiteParser.Tools.ReadColumnToField[str](record, 'NID', cell.NID, self.extract_source, str)
            SQLiteParser.Tools.ReadColumnToField[str](record, 'BSID', cell.BID, self.extract_source, str)

            self.get_timestamp_from_record(record, result.TimeStamp)
            cell.TimeStamp.Init(result.TimeStamp)
            self.get_description_from_record(record, result.Description, ['MCC', 'SID', 'NID', 'BSID'])
            self.get_coordinate_and_data_from_record(record, result)
            cell.Position.Value = result.Position.Value
            results.append(result)
            if cell.HasLogicalContent:
                results.Add(cell)
        return results

    def parse_wifi_locations(self):
        if self.db is None or 'WifiLocation' not in self.db.Tables:
            return []
        ts = SQLiteParser.TableSignature('WifiLocation')
        if self.extract_deleted:
            ts['Latitude'] = ts['Longitude'] = ts['Timestamp'] = SQLiteParser.Signatures.NumericSet(7)
            ts['Confidence'] = SQLiteParser.Signatures.NumericSet(1)
            ts['HorizontalAccuracy'] = SQLiteParser.Signatures.SignatureFactory.GetFieldSignature(SQLiteParser.FieldType.Int)
            ts['MAC'] = TextNotNull

        results = []
        for record in self.db.ReadTableRecords(ts, self.extract_deleted, True):
            if not self.validate_coordinate(record):
                continue

            result = Location()
            result.Deleted = record.Deleted
            result.Category.Value = LocationCategories.WIFI_NETWORKS

            self.get_timestamp_from_record(record, result.TimeStamp)
            self.get_mac_from_record(record, result.Description)
            self.get_coordinate_and_data_from_record(record, result)
            results.append(result)

        return results

    def parse_location_harvest(self):
        if self.db is None or 'LocationHarvest' not in self.db.Tables:
            return []

        ts = SQLiteParser.TableSignature('LocationHarvest')
        if self.extract_deleted:
            ts['Latitude'] = ts['Longitude'] = ts['Timestamp'] = SQLiteParser.Signatures.NumericSet(7)
            ts['Confidence'] = SQLiteParser.Signatures.NumericSet(1)
            ts['MCC'] = ts['MNC'] = SQLiteParser.Signatures.NumericRange(1, 4)
            ts['HorizontalAccuracy'] = SQLiteParser.Signatures.SignatureFactory.GetFieldSignature(SQLiteParser.FieldType.Int)
        results = []
        for record in self.db.ReadTableRecords(ts, self.extract_deleted, True):
            if not self.validate_coordinate(record):
                continue

            result = Location()
            result.Deleted = record.Deleted
            result.Category.Value = LocationCategories.HARVESTED

            self.get_timestamp_from_record(record, result.TimeStamp)
            self.get_description_from_record(record, result.Description, ['MCC', 'MNC'])
            self.get_coordinate_and_data_from_record(record, result)
            if result.Deleted == DeletedState.Intact or self.is_good_coordinate(result.Position.Value) or self.is_good_description(result.Description.Value) or result.TimeStamp.HasContent:
                results.append(result)

        return results

    def parse_wifi_location_harvest(self):
        if self.db is None or 'WifiLocationHarvest' not in self.db.Tables:
            return []
        ts = SQLiteParser.TableSignature('WifiLocationHarvest')
        if self.extract_deleted:
            ts['Latitude'] = ts['Longitude'] = ts['Timestamp'] = SQLiteParser.Signatures.NumericSet(7)
            ts['HorizontalAccuracy'] = SQLiteParser.Signatures.SignatureFactory.GetFieldSignature(SQLiteParser.FieldType.Int)
            ts['Confidence'] = ts['Channel'] = SQLiteParser.Signatures.NumericSet(1)
            ts['MAC'] = TextNotNull

        results = []
        for record in self.db.ReadTableRecords(ts, self.extract_deleted, True):
            if not self.validate_coordinate(record):
                continue

            result = Location()
            result.Deleted = record.Deleted
            result.Category.Value = 'Harvested Wifi Locations'

            wn = WirelessNetwork()
            wn.Deleted = result.Deleted
            self.get_mac_from_record(record, wn.BSSId)
            
            self.get_timestamp_from_record(record, result.TimeStamp)
            wn.TimeStamp.Init(result.TimeStamp)
            self.get_mac_from_record(record, result.Description)
            self.get_coordinate_and_data_from_record(record, result)
            if result.Deleted != DeletedState.Intact and not self.is_good_coordinate(result.Position.Value):
                result.Position.Value = None
            wn.Position.Value = result.Position.Value
            LinkModels(wn, result) 
            results.append(result)            
            if wn.HasLogicalContent:
                results.append(wn)

        return results

    def parse_cell_location_harvest(self):
        if self.db is None or 'CellLocationHarvest' not in self.db.Tables:
            return []
        ts = SQLiteParser.TableSignature('CellLocationHarvest')
        if self.extract_deleted:
            ts['Latitude'] = ts['Longitude'] = ts['Timestamp'] = SQLiteParser.Signatures.NumericSet(7)
            ts['Confidence'] = SQLiteParser.Signatures.NumericSet(1)
            ts['HorizontalAccuracy'] = SQLiteParser.Signatures.SignatureFactory.GetFieldSignature(SQLiteParser.FieldType.Int)
            ts['MCC'] = ts['MNC'] = SQLiteParser.Signatures.NumericRange(1, 2)
            ts['LAC'] = SQLiteParser.Signatures.NumericRange(1, 3)
            ts['CI'] = SQLiteParser.Signatures.NumericRange(1, 4)
            ts['Operator'] = TextNotNull

        results = []
        for record in self.db.ReadTableRecords(ts, self.extract_deleted, True):
            if not self.validate_coordinate(record):
                continue

            result = Location()
            result.Deleted = record.Deleted
            result.Category.Value = "Harvested Cell Towers"
            self.get_timestamp_from_record(record, result.TimeStamp)
            self.get_description_from_record(record, result.Description, ['Operator', 'MCC', 'MNC', 'LAC', 'CI'])
            self.get_coordinate_and_data_from_record(record, result)
            results.append(result)

        return results

    def parse_reminder_locations(self):
        if self.db is None or 'Fences' not in self.db.Tables:
            return []
        calendar = None
        names = {}
        for fs in self.ds.FileSystems:
            for d in fs.GetAllNodes(NodeType.Directory):
                if d.Name == 'Calendar':
                    calendar = d.GetByPath('Calendar.sqlitedb')
                    if calendar:
                        break
            if calendar:
                break

        if calendar:
            calendar_db = SQLiteParser.Database.FromNode(calendar)
            if calendar_db is not None:
                temp_dict = {}

                calendar_ts = SQLiteParser.TableSignature('Alarm')
                if self.extract_deleted:
                    calendar_ts['owner_id'] = SQLiteParser.Signatures.NumericSet(6)
                    calendar_ts['calendaritem_owner_id'] = SQLiteParser.Signatures.NumericSet(6)
                for record in calendar_db.ReadTableRecords(calendar_ts, self.extract_deleted, True):
                    owner = 'owner_id'
                    if 'calendaritem_owner_id' in record:
                        owner = 'calendaritem_owner_id'

                    if not 'UUID' in record:
                        continue
                    temp_dict[record[owner].Value] = [record['UUID'].Value]

                if 'CalendarItem' in calendar_db.Tables:
                    ts = SQLiteParser.TableSignature('CalendarItem')
                    if self.extract_deleted:
                        ts['summary'] = TextNotNull
                    for record in calendar_db.ReadTableRecords(ts, self.extract_deleted):
                        if record['ROWID'].Value in temp_dict:
                            temp_dict[record['ROWID'].Value].append(record['summary'])

                for key in temp_dict:
                    if len(temp_dict[key]) == 2:
                        names[temp_dict[key][0]] = temp_dict[key][1]

        ts = SQLiteParser.TableSignature('Fences')
        if self.extract_deleted:
            ts['Latitude'] = ts['Longitude'] = SQLiteParser.Signatures.NumericSet(7)
            ts['Timestamp'] = SQLiteParser.Signatures.NumericSet(4, 7)
        results = []
        for record in self.db.ReadTableRecords(ts, self.extract_deleted, True):
            if not self.validate_coordinate(record) or record['Timestamp'].Value == 0:
                continue

            result = Location()
            result.Deleted = record.Deleted
            result.Category.Value = LocationCategories.REMINDER

            SQLiteParser.Tools.ReadColumnToField(record, 'BundleId', result.Description, self.extract_source)
            self.get_timestamp_from_record(record, result.TimeStamp)

            if not IsDBNull(record['Name'].Value) and record['Name'].Value in names:
                result.Name.Value = names[record['Name'].Value].Value
                if self.extract_source:
                    result.Name.Source = MemoryRange(names[record['Name'].Value].Source)

            cor = self.get_coordinate(record)
            if cor is not None:
                result.Position.Value = cor

            if result.Deleted == DeletedState.Intact or result.TimeStamp.HasContent or self.is_good_coordinate(cor) or self.is_good_description(result.Description.Value):
                results.append(result)

        return results

    def is_good_coordinate(self, cor):
        '''Most false positives have very small coordinates (like (9.17454077345e-67, 3.37215970892e-102))'''
        if cor is None or cor.Latitude.Value is None or cor.Longitude.Value is None:
            return False
        return cor.Latitude.Value**2 + cor.Longitude.Value**2 > 0.5

    def is_good_description(self, desc):
        if desc is None:
            return False
        return all(c in string.printable for c in desc)

    def parse_app_harvest_locations(self):
        if self.db is None or 'AppHarvest' not in self.db.Tables:
            return []
        ts = SQLiteParser.TableSignature('AppHarvest')
        if self.extract_deleted:
            ts['Latitude'] = ts['Longitude'] = ts['Timestamp'] = SQLiteParser.Signatures.NumericSet(7)
            ts['Confidence'] = SQLiteParser.Signatures.NumericSet(1)
            ts['HorizontalAccuracy'] = SQLiteParser.Signatures.SignatureFactory.GetFieldSignature(SQLiteParser.FieldType.Int)
            ts['BundleId'] = TextNotNull

        results = []
        for record in self.db.ReadTableRecords(ts, self.extract_deleted, True):
            if not self.validate_coordinate(record):
                continue

            result = Location()
            result.Deleted = record.Deleted
            result.Category.Value = "Application Locations"
            self.get_timestamp_from_record(record, result.TimeStamp)
            SQLiteParser.Tools.ReadColumnToField(record, 'BundleId', result.Description, self.extract_source)
            self.get_coordinate_and_data_from_record(record, result)
            results.append(result)

        return results

    def parse(self):
        if self.db is None:
            return []
        results = []
        results += self.parse_cell_locations()
        results += self.parse_cdma_cell_location()
        results += self.parse_wifi_locations()
        results += self.parse_location_harvest()
        results += self.parse_wifi_location_harvest()
        results += self.parse_cell_location_harvest()
        results += self.parse_reminder_locations()
        results += self.parse_app_harvest_locations()
        return results

def analyze_locations(node, extract_deleted, extract_source):
    pr = ParserResults()
    pr.Models.AddRange(LocationsParser(node, extract_deleted, extract_source).parse())
    return pr

class FrequentLocationsParser(object):
    def __init__(self, root, extractDeleted, extractSource):
        self.root = root
        self.extractSource = extractSource
        self.extractDeleted = extractDeleted
        self.category = LocationCategories.FREQUENT_LOCATIONS

    def parse(self):
        results = []

        results.extend(self.parseLocationsDB())
        results.extend(self.parseStateModels())
        return results

    def parseLocationsDB(self):
        results = []

        dbNode = self.root.GetByPath('/cache_encryptedB.db')
        if dbNode is None or dbNode.Data is None:
            return results

        db = SQLiteParser.Database.FromNode(dbNode)
        if db is None:
            return results

        locationTables = [tableName for tableName in ['RoutineLocation', 'Location', 'Hint'] if tableName in db.Tables]

        for locTableName in locationTables:
            ts = SQLiteParser.TableSignature(locTableName)
            if self.extractDeleted:
                SQLiteParser.Tools.AddSignatureToTable(ts, 'Timestamp', SQLiteParser.Tools.SignatureType.Float)
                SQLiteParser.Tools.AddSignatureToTable(ts, 'Latitude', SQLiteParser.Tools.SignatureType.Float)
                SQLiteParser.Tools.AddSignatureToTable(ts, 'Longitude', SQLiteParser.Tools.SignatureType.Float)
                SQLiteParser.Tools.AddSignatureToTable(ts, 'HorizontalAccuracy', SQLiteParser.Tools.SignatureType.Byte, SQLiteParser.Tools.SignatureType.Int)
            for rec in db.ReadTableRecords(ts, self.extractDeleted, True):
                if IsDBNull(rec['Latitude'].Value) or IsDBNull(rec['Longitude'].Value):
                    continue

                coor = Coordinate()
                SQLiteParser.Tools.ReadColumnToField(rec, 'Latitude', coor.Latitude, self.extractSource)
                SQLiteParser.Tools.ReadColumnToField(rec, 'Longitude', coor.Longitude, self.extractSource)
                if 'Altitude' in rec:
                    SQLiteParser.Tools.ReadColumnToField[float](rec, 'Altitude', coor.Elevation, self.extractSource, float)

                loc = Location()
                loc.Category.Value = self.category
                loc.Deleted = rec.Deleted
                loc.Position.Value = coor
                SQLiteParser.Tools.ReadColumnToField[str](rec, 'HorizontalAccuracy', loc.Precision, self.extractSource, str)
                SQLiteParser.Tools.ReadColumnToField[TimeStamp](rec, 'Timestamp', loc.TimeStamp, self.extractSource, lambda t: TimeStamp(epoch.AddSeconds(t), True))

                results.append(loc)

        return results

    def parseStateModels(self):
        results = []

        sm1Node = self.root.GetByPath('/StateModel1.archive')
        sm2Node = self.root.GetByPath('/StateModel2.archive')
        sm1 = BPReader.GetTree(sm1Node) if sm1Node is not None else None
        sm2 = BPReader.GetTree(sm2Node) if sm2Node is not None else None
        sm = self.ChooseStateModel(sm1, sm2)
        if sm is None:
            return results
        for state in sm['stateModelLut']:
            stateNode = state
            locationNode = stateNode['stateDepiction/clusterState/location']
            placeResultNode = stateNode['stateDepiction/clusterState/placeResult/data/NS.data']
            if locationNode is None and placeResultNode is None:
                continue

            loc = Location()
            loc.Category.Value = self.category
            loc.Deleted = DeletedState.Intact

            if locationNode is not None:
                coor = Coordinate()
                coor.Latitude.Init(locationNode['Latitude_deg'].Value, MemoryRange(locationNode['Latitude_deg'].Source) if self.extractSource else None)
                coor.Longitude.Init(locationNode['Longitude_deg'].Value, MemoryRange(locationNode['Longitude_deg'].Source) if self.extractSource else None)
                loc.Position.Value = coor

                loc.Precision.Init(str(locationNode['uncertainty_m'].Value), MemoryRange(locationNode['uncertainty_m'].Source) if self.extractSource else None)
            if placeResultNode is not None:
                loc.Address.Value = self.getAddressFromPlaceResult(placeResultNode.Value)

            historyList = stateNode['stateDepiction/clusterState/histEntryExit_s']
            # 如果没有访问记录,则作为地理位置信息模型添加
            if historyList is None:
                results.append(loc)
                continue

            # 创建访问记录
            for visitNode in historyList.Value:
                j = Journey()
                j.Source.Value = self.category
                j.Deleted = DeletedState.Intact
                j.WayPoints.Add(loc)
                j.StartTime.Init(TimeStamp(epoch.AddSeconds( visitNode['entry_s'].Value), True), MemoryRange(visitNode['entry_s'].Source) if self.extractSource else None)
                j.EndTime.Init(TimeStamp(epoch.AddSeconds( visitNode['exit_s'].Value), True), MemoryRange(visitNode['exit_s'].Source) if self.extractSource else None)
                results.append(j)

        return results

    def ChooseStateModel(self, sm1, sm2):
        # 优先返回不为空的
        if sm1 is None:
            if sm2 is None:
                return None
            else:
                return sm2
        elif sm2 is None:
            return sm1

        version1 = sm1['version'].Value
        version2 = sm2['version'].Value
        # 返回有版本信息的plist
        if version1 is None:
            if version2 is None:
                return None
            else:
                return sm2
        elif version2 is None:
            return sm1

        # 优先选择高版本的
        return sm1 if version1 >= version2 else sm2

    def getAddressFromPlaceResult(self, data):
        stream = StringIO(''.join(map(chr,data)))
        stream.seek(6) # 前6个字节不需要
        stream.seek(ord(stream.read(1)), os.SEEK_CUR) # 跳过第一个字段

        x = stream.read(1)
        while (x != '\x5A'):
            if x == '':
                return
            x = stream.read(1)
        street = stream.read(ord(stream.read(1))) # 读取街道地址
        stream.read(1)
        city = stream.read(ord(stream.read(1))) # 读取城市
        stream.read(1)
        country = stream.read(ord(stream.read(1))) # 读取国家

        addr = StreetAddress()
        addr.Deleted = DeletedState.Intact
        addr.Category.Value = self.category
        addr.Street1.Value = street
        addr.City.Value = city
        addr.Country.Value = country

        return addr


"""
常去地地点数据解析(iOS7+)
"""
def analyze_frequent_locations(root, extractDeleted, extractSource):
    pr = ParserResults()
    pr.Models.AddRange(FrequentLocationsParser(root, extractDeleted, extractSource).parse())
    return pr


"""
封装苹果地图处理类
"""
class apple_maps(object):
    valueSourcePair = namedtuple("valueSourcePair", "Value Source")
    TLV = namedtuple("TLV", "Type Length Value")

    def __init__(self, root, extractDeleted, extractSource):
        self.root = root
        self.extractDeleted = extractDeleted
        self.extractSource = extractSource

    def parse_variable_integer(self, mem, nPointer, endianity):
        num = 0
        l = 0
        more = True
        mem.seek(nPointer)
        while more:
            if nPointer + l > mem.Length:
                return 0, 0
            byte = mem.ReadByte()
            more = (byte & 0x80 != 0x00)
            if endianity == "LE":
                num += (byte & 0x7F) << (l * 7)
            elif endianity == "BE":
                num = (num << (l * 7)) + (byte & 0x7F)
            else:
                return 0, 0
            l += 1
        return l, num

    def parseTLV(self, mem, nPointer, endianity):        
        typeL, type = self.parse_variable_integer(mem, nPointer, endianity)        
        typeSource = mem.GetSubRange(nPointer, typeL)
        nPointer += typeL
        if nPointer > mem.Length or typeL == 0:
            ## if we exceed the size of the file, we return the end of it as the new nPointer. If the curr type length is 0, we also return the end of the stream as nPointer
            return self.TLV(self.valueSourcePair(type, typeSource), self.valueSourcePair(0, None), self.valueSourcePair("", None)), mem.Length
        lengthL, length = self.parse_variable_integer(mem, nPointer, endianity)
        lengthSource = mem.GetSubRange(nPointer, lengthL)
        nPointer += lengthL
        if nPointer > mem.Length or nPointer + length > mem.Length:
            return self.TLV(self.valueSourcePair(type, typeSource), self.valueSourcePair(length, lengthSource), self.valueSourcePair("", None)), mem.Length
        mem.seek(nPointer)
        value = mem.read(length)
        valueSource = mem.GetSubRange(nPointer, length)
        nPointer += length
        return self.TLV(self.valueSourcePair(type, typeSource), self.valueSourcePair(length, lengthSource), self.valueSourcePair(value, valueSource)), nPointer

    def parseCoordinates(self, value, endianity):
        if len(value.Value) < 0x24:
            return None
        lat_chunks = []
        lon_chunks = []
        if endianity == "LE":
            type1, lat1, type2, lon1, type3, lat2, type4, lon2 = struct.unpack('<BdBdBdBd',value.Value[:0x24])
        elif endianity == "BE":
            type1, lat1, type2, lon1, type3, lat2, type4, lon2 = struct.unpack('>BdBdBdBd',value.Value[:0x24])
        else:
            return None
        if (type1, type2, type3, type4) == (0x29, 0x31, 0x39, 0x41):
            c = Coordinate((lat1 + lat2) / 2, (lon1 + lon2) / 2)
            if self.extractSource:
                lat_chunks.extend(value.Source.GetSubRange(0x01, 8).Chunks)
                lat_chunks.extend(value.Source.GetSubRange(0x11, 8).Chunks)
                lon_chunks.extend(value.Source.GetSubRange(0x09, 8).Chunks)
                lon_chunks.extend(value.Source.GetSubRange(0x19, 8).Chunks)
                c.Latitude.Source = MemoryRange(lat_chunks)
                c.Longitude.Source = MemoryRange(lon_chunks)
            return c
        return None

    def parseAddress(self, value, endianity):
        nPointer = 0
        tlv, nPointer = self.parseTLV(value.Source, nPointer, endianity)
        if nPointer == 0 and tlv is not None:
            return None
        while tlv.Type.Value != 0x7A and nPointer < value.Source.Length:
            tlv, nPointer = self.parseTLV(value.Source, nPointer, endianity)
            if tlv.Length.Value == 0x00:
                break 
        if tlv.Type.Value == 0x7A:
            address = StreetAddress()
            address.Deleted = DeletedState.Intact
            nPointer = 0
            data = tlv.Value
            while nPointer < len(data.Value):
                tlv, nPointer = self.parseTLV(data.Source, nPointer, endianity)
                if tlv is None:
                    return None
                field = None
                if tlv.Type.Value == 0x7A:
                    field = address.Country
                elif tlv.Type.Value == 0x1A:
                    field = address.State
                elif tlv.Type.Value == 0x32:
                    field = address.City
                elif tlv.Type.Value == 0x3A:
                    field = address.PostalCode
                elif tlv.Type.Value == 0x52:
                    field = address.Street1
                elif tlv.Type.Value == 0x5A:
                    field = address.HouseNumber                
                elif tlv.Type.Value == 0x62 and address.Street1.Value is None:
                    field = address.Street1
                elif tlv.Type.Value == 0x8A:
                    break
                if field is not None:
                    if tlv.Type.Value == 0x5A:
                        try:
                            field.Value = int(tlv.Value.Value)
                        except:
                            pass
                    else:
                        field.Value = tlv.Value.Value.decode('utf8')
                    if self.extractSource:
                        field.Source = tlv.Value.Source
                if address.HasContent:
                    return address
        return None

    def analyze_maps_bookmarks(self):
        node = self.root.GetByPath("Bookmarks.plist")
        endianity = "LE"
        if node is None:
            geo_node = self.root.GetByPath("GeoBookmarks.plist")
            if geo_node is None:
                return []
            bp = BPReader.GetTree(geo_node)
            if bp is None:
                return []
            if not bp.ContainsKey("MSPBookmarks"):
                return []
            results = []
            for bookmark in bp["MSPBookmarks"]:
                results += self.parse_apple_geohistory(MemoryRange(bookmark.Source), True)
            return results
        results = []
        try:
            bp = BPReader(node.Data).top
        except:
            return results
        if bp is None:
            return results
        if 'BookmarksData' not in bp.Keys:
            return results
        for i in range(bp['BookmarksData'].Length):
            ## older format of bookamrks was discoverd, for now it will be try catch to avoid exceptions. but it will be taken care of 
            try:
                loc = Location()
                loc.Deleted = DeletedState.Intact
                loc.Category.Value = 'Maps Bookmarks'
                mem = MemoryRange(bp['BookmarksData'][i].Source)
                start = 0x10
                lengthLength, length = self.parse_variable_integer(mem, start, endianity)
                start += lengthLength
                mem.seek(0)
                data = mem.read()            
                nPointer = data.index('\x22', start)         
                while nPointer < mem.Length:
                    tlv, nPointer = self.parseTLV(mem, nPointer, endianity)
                    if tlv is None:
                        return results
                    if tlv.Type.Value == 0x22:
                        loc.Name.Value = tlv.Value.Value.decode('utf8')
                        if self.extractSource:
                            loc.Name.Source = tlv.Value.Source
                    elif tlv.Type.Value == 0x2A:
                        loc.Position.Value = self.parseCoordinates(tlv.Value, endianity)
                    elif tlv.Type.Value == 0x32:
                        loc.Address.Value = self.parseAddress(tlv.Value, endianity)
                    else:
                        results.append(loc)
                        break
            except:
                continue
        return results
    
    def _read_unknon_pos_data(self, stream, endianity):
        start = stream.tell()
        unknown = stream.read(0x13) 
        
        next = stream.read(0x1)
        
        if next == '\x01':
            self.parse_variable_integer(stream, stream.tell(), endianity)
        else: 
            stream.seek(stream.tell()-1)
        next = stream.read(0x1)
        if next == '\x18':
            self.parse_variable_integer(stream, stream.tell(), endianity)
        else: 
            stream.seek(stream.tell()-1)
        end = stream.tell()
        return end - start

    def parse_navigation(self, innerTLV, endianity, deleted_state):
        innerData = innerTLV.Value.Source
        innerPointer = 0
        j = Journey()
        j.Deleted = deleted_state
        locations = {"from": None, 
                     "to": None}
        while innerPointer < innerData.Length:
            innerTLV, innerPointer = self.parseTLV(innerData, innerPointer, endianity)
            l = Location()
            l.Deleted = deleted_state
            if innerTLV.Type.Value == 0x0A:
                location_type = "from"
                locations["from"] = l
            elif innerTLV.Type.Value == 0x12:
                location_type = "to"
                locations["to"] = l
            else: break

            data =innerTLV.Value.Source
            locationPointer = self._read_unknon_pos_data(data, endianity)
            while locationPointer < data.Length:
                    locationTLV, locationPointer = self.parseTLV(data, locationPointer, endianity)
                    #location name
                    if locationTLV.Type.Value == 0x22: 
                        l.Name.Init(locationTLV.Value.Value.decode('utf8') ,MemoryRange(locationTLV.Value.Source) if self.extractSource else None)
                        if not j.Name.Value: j.Name.Value = ""
                        j.Name.Value += "{0}: {1}\n".format(location_type, locationTLV.Value.Value.decode('utf8'))
                    #location regular coordinates
                    elif locationTLV.Type.Value == 0x2A:
                        location_pos = self.parseCoordinates(locationTLV.Value, endianity)
                        if location_pos:
                            l.Position.Value = location_pos      
                    #shown coordinates
                    elif locationTLV.Type.Value == 0x4A:
                        location_pos = self.parseCoordinates(locationTLV.Value, endianity)
                        if location_pos:
                            if not l.Position.HasContent:
                                l.Position.Value = location_pos  
                            LinkModels(l, location_pos)
                    #Address
                    elif locationTLV.Type.Value == 0x32:
                        l.Address.Value = self.parseAddress(locationTLV.Value, endianity)
                    if locationTLV.Type.Value in [0x90, 0x60]: break
        for l in locations.values():
            if l:
                j.WayPoints.Add(l)
        if locations["from"]:
            j.FromPoint.Value = locations["from"]
        if locations["to"]:
            j.ToPoint.Value = locations["to"]
        return j

    def parse_apple_maps_history_tlv(self, mem, node):
        results = []
        nPointer = 0
        endianity = "LE"
        lastPointer = nPointer
        while nPointer < mem.Length:
            tlv, nPointer = self.parseTLV(mem, nPointer, endianity)
            
            if tlv is None:
                return results
            search = SearchedItem()
            search.Deleted = DeletedState.Intact
            search.Source.Value = 'Maps'
            loc_name = None
            position = None
            if tlv.Type.Value == 0x52:
                innerTLV, innerPointer = self.parseTLV(tlv.Value.Source, 0, endianity)
                if innerTLV.Type.Value == 0x52:
                    innerData = innerTLV.Value.Source
                    innerPointer = 0
                    while innerPointer < innerData.Length:
                        innerTLV, innerPointer = self.parseTLV(innerData, innerPointer, endianity)
                        if innerTLV.Type.Value == 0x52:
                            tempPointer = 0
                            while tempPointer < innerTLV.Value.Source.Length:
                                tempTLV, tempPointer = self.parseTLV(innerTLV.Value.Source, tempPointer, endianity)
                                if tempTLV.Type.Value == 0x2A:
                                    search.Value.Value = tempTLV.Value.Value.decode('utf8')                                    
                                    if self.extractSource:
                                        search.Value.Source = tempTLV.Value.Source                                    
                                    loc_name = search.Value                                        
                                elif tempTLV.Type.Value == 0x32:
                                    position = self.parseCoordinates(tempTLV.Value, endianity)
                                else:
                                    results.append(search)
                                    break
                        elif innerTLV.Type.Value == 0xC2:
                            tempPointer  = 0                            
                            while tempPointer < innerTLV.Value.Source.Length:
                                tempTLV, tempPointer = self.parseTLV(innerTLV.Value.Source, tempPointer, endianity)
                                if tempTLV.Type.Value == 0x12:
                                    loc = Location()
                                    loc.Deleted = DeletedState.Intact
                                    loc.Category.Value = 'Maps Search'
                                    locName = []
                                    locNameChunks = []
                                    if loc_name is not None:
                                        locName.append(loc_name.Value)
                                        if not loc_name.Source: loc_name.Source = MemoryRange()
                                        locNameChunks.extend(loc_name.Source.Chunks)
                                    anotherTempPointer = 0
                                    while anotherTempPointer < tempTLV.Length.Value:
                                        anotherTempTLV, anotherTempPointer = self.parseTLV(tempTLV.Value.Source, anotherTempPointer, endianity)
                                        if anotherTempTLV.Type.Value == 0x0A:
                                            locationData = anotherTempTLV.Value.Source
                                            locationPointer = 0
                                            while locationPointer < len(anotherTempTLV.Value.Value) and anotherTempTLV.Value.Value[locationPointer] not in ['\x22', '\x2A', '\x32']:
                                                locationPointer += 1
                                            while locationPointer < locationData.Length:
                                                locationTLV, locationPointer = self.parseTLV(locationData, locationPointer, endianity)
                                                if locationTLV.Type.Value == 0x2A:
                                                    loc.Position.Value = self.parseCoordinates(locationTLV.Value, endianity)
                                                elif locationTLV.Type.Value == 0x22:
                                                    locName.append(locationTLV.Value.Value)
                                                    if self.extractSource and locationTLV.Value.Source is not None:
                                                        locNameChunks.extend(locationTLV.Value.Source.Chunks)
                                                elif locationTLV.Type.Value == 0x32:                                                    
                                                    loc.Address.Value = self.parseAddress(locationTLV.Value, endianity)
                                                else:
                                                    break
                                            #the string sometimes is already unicoded then we can't decode it again to utf8 (we are getting UnicodeEncodeError: ('unknown', '\x00', 0, 1, ''))
                                            #and if we get's an UnicodeEncodeError we are assuming that the string is already good (decoded to utf8)
                                            try:
                                                loc.Name.Value = u' '.join(locName).decode("utf8")
                                            #the string probably already decoded
                                            except UnicodeDecodeError:
                                                loc.Name.Value = u' '.join(locName)
                                            except UnicodeEncodeError:
                                                loc.Name.Value = u' '.join(locName)
                                            if self.extractSource:
                                                loc.Name.Source = MemoryRange(locNameChunks)
                                        elif anotherTempTLV.Type.Value == 0x11:
                                            break                                 
                                    results.append(loc)
                                else:
                                    pass
                        else:
                            pass               
                elif innerTLV.Type.Value == 0x62:
                    journey = self.parse_navigation(innerTLV, endianity, node.Deleted)
                    if journey:
                        results.append(journey)
            else:
                pass
            ##fix endless loop nPointer not moving
            if nPointer == lastPointer:
                break
            else: lastPointer = nPointer  
        return results

    def analyze_maps_history(self):
        results = []
        node = self.root.GetByPath("History.mapsdata")
        if not (node is None or node.Data is None):      
            results += self.parse_apple_maps_history_tlv(node.Data, node)
        geonode = self.root.GetByPath("GeoHistory.mapsdata")
        if geonode is None or geonode.Data is None:
            return results
        geobp = BPReader.GetTree(geonode)
        if geobp is None:
            return results
        if geobp.ContainsKey('MSPHistory'):
            for item in geobp['MSPHistory'].Value:
                results += self.parse_apple_geohistory(MemoryRange(item.Value.Source))
        return results

    def parse_apple_geohistory(self, mem, is_bookmark = False):
        mem.seek(0)
        locs = []
        endianity = "LE"
        esign = self.get_endianity_sign(endianity)
        data = mem.read()
        if len(data) == 0:
            return locs
        num_of_blocks = ord(data[1])
        data_idx = 0x28
        if len(data) >= data_idx+1+8:
            timestamp = TimeStampFormats.GetTimeStampEpoch1Jan2001(int(struct.unpack(esign+'d',data[data_idx+1:data_idx + 1 + 8])[0]))
        else:
            return locs
        if num_of_blocks > 1:
            data_idx += ord(data[data_idx]) + 1
            if data_idx >= len(data):
                self.add_positions_heuristically(locs, timestamp, data, mem, endianity)
                return locs
            data_idx += ord(data[data_idx]) + 1
            if (data_idx + 1) >= len(data):
                self.add_positions_heuristically(locs, timestamp, data, mem, endianity)
                return locs
            data_idx += ord(data[data_idx + 1]) + 2
            if data_idx >= len(data):
                self.add_positions_heuristically(locs, timestamp, data, mem, endianity)
                return locs
            if data[data_idx] == '\x12':
                while data_idx < mem.Length:
                    block_data, end_pointer = self.parseTLV(mem, data_idx, endianity)
                    # ticket 1174205, invalid tlv
                    if block_data.Value.Value == '':
                        break
                    block_mem = MemoryRange(block_data.Value.Source)
                    position = self.get_block_positions(block_mem, endianity, ['\x0a\x12','\x0a\x24', '\x2a\x24', '\x4a\x12'])
                    locs.append(self.create_location(position, timestamp))
                    block_position_data, end_pointer = self.parseTLV(mem, end_pointer, endianity)
                    if block_position_data.Type.Value == 0x1a:
                        block_position = self.parseCoordinates12(block_position_data.Value, endianity)
                    end_pointer += 1
                    end_pointer += 6
                    if end_pointer > len(data):
                        break
                    end_pointer = self.parseTLV(mem, end_pointer, endianity)[1]
                    data_idx = end_pointer
            else:
                self.add_positions_heuristically(locs, timestamp, data, mem, endianity)
        else:
            position = self.get_block_positions(mem, endianity, ['\x22\x24'])
            description = self.get_single_block_description(mem, endianity)
            l = self.create_location(position,timestamp)
            if is_bookmark:
                l.Category.Value = "Apple Maps Bookmarks"
            l.Description.Value = description
            l.Position.Value = position
            locs.append(l)
        return locs

    def add_positions_heuristically(self, locs, timestamp, data, mem, endianity):
        positions = self.get_all_positions(data, mem, endianity)
        for p in positions:
            locs.append(self.create_location(p, timestamp))

    def get_all_positions(self,data, mem, endianity):
        positions = []
        end_pointer = 0
        data_idx = data.find('\x1a\x12',end_pointer)
        while data_idx != -1:
            block_mem = mem.GetSubRange(data_idx, 0x14)
            position = self.get_block_positions(block_mem, endianity, ['\x1a\x12'])
            positions.append(position)
            end_pointer = data_idx + 0x14
            data_idx = data.find('\x1a\x12',end_pointer)
        end_pointer = 0
        data_idx = data.find('\x4a\x12',end_pointer)
        while data_idx != -1:
            block_mem = mem.GetSubRange(data_idx, 0x14)
            position = self.get_block_positions(block_mem, endianity, ['\x4a\x12'])
            positions.append(position)
            end_pointer = data_idx + 0x14
            data_idx = data.find('\x4a\x12',end_pointer)
        return positions

    def get_single_block_description(self, mem, endianity):
        curr_ptr = 0x3a 
        data, curr_ptr = self.parseTLV(mem, curr_ptr, endianity) 
        if data.Type.Value == 0x32:
            data, curr_ptr = self.parseTLV(data.Value.Source, 0, endianity) 
            if data.Type.Value == 0x0a:
                return data.Value.Value.decode('utf8')


    def create_location(self, position, timestamp):
        l = Location()
        l.Position.Value = position
        l.Deleted = DeletedState.Intact
        l.Category.Value = "Apple Maps"
        timeStamp = TimeStamp(timestamp,True)
        if timeStamp.IsValidForSmartphone():
            l.TimeStamp.Value = timeStamp
        return l

    def get_block_positions(self, mem, endianity, sig_list):
        positions = []
        mem.seek(0)
        data = mem.read()
        for i in sig_list:
            curr_idx = data.find(i)
            while curr_idx != -1:
                TLV = self.parseTLV(mem, curr_idx, endianity)[0]
                if ord(i[1]) == 0x12:
                    positions.append(self.parseCoordinates12(TLV.Value, endianity))
                elif ord(i[1]) == 0x24:
                    positions.append(self.parseCoordinates(TLV.Value, endianity))
                curr_idx = data.find('i', curr_idx+1)
            mem.seek(0)
        curr_idx = data.find('\x0a\x24')
        while curr_idx != -1:
            TLV = self.parseTLV(mem, curr_idx, endianity)[0]
            positions.append(self.parseCoordinates(TLV.Value, endianity))
            curr_idx = data.find('\x0a\x24', curr_idx+1)
        mem.seek(0)
        curr_idx = data.find('\x22\x24')
        while curr_idx != -1:
            TLV = self.parseTLV(mem, curr_idx, endianity)[0]
            positions.append(self.parseCoordinates(TLV.Value, endianity))
            curr_idx = data.find('\x22\x24', curr_idx+1)
        return self.average_positions(positions)
        
    def average_positions(self, positions):
        avg_pos = (0,0)
        lat_sources = []
        lon_sources = []
        valid_pos_num = 0
        for pos in positions:
            if pos is None:
                continue
            if abs(pos.Latitude.Value) < 90 and pos.Latitude.Value != 0 and abs(pos.Longitude.Value) < 180 and pos.Longitude.Value != 0:
                avg_pos = (avg_pos[0] + pos.Latitude.Value, avg_pos[1] + pos.Longitude.Value)
                if self.extractSource:
                    if pos.Latitude.Source is not None:
                        lat_sources.extend(pos.Latitude.Source.Chunks)
                    if pos.Longitude.Source is not None:
                        lon_sources.extend(pos.Longitude.Source.Chunks)
                valid_pos_num += 1
        if valid_pos_num == 0:
            return None
        c = Coordinate(avg_pos[0] / valid_pos_num, avg_pos[1] / valid_pos_num)
        if self.extractSource:
            c.Latitude.Source = MemoryRange(lat_sources)
            c.Longitude.Source = MemoryRange(lon_sources)
        return c

    def get_endianity_sign(self, endianity):
        if endianity == 'LE':
            return '<'
        else:
            return '>'
    
    def parseCoordinates12(self, value, endianity):
        if len(value.Value) < 0x12:
            return None
        lat_chunks = []
        lon_chunks = []
        if endianity == "LE":
            type1, lat1, type2, lon1 = struct.unpack('<BdBd',value.Value[:0x12])
        elif endianity == "BE":
            type1, lat1, type2, lon1 = struct.unpack('>BdBd',value.Value[:0x12])
        else:
            return None
        if (type1, type2) == (0x09, 0x011):
            c = Coordinate(lat1, lon1)
            if self.extractSource:
                lat_chunks.extend(value.Source.GetSubRange(0x01, 8).Chunks)
                lon_chunks.extend(value.Source.GetSubRange(0x09, 8).Chunks)
                c.Latitude.Source = MemoryRange(lat_chunks)
                c.Longitude.Source = MemoryRange(lon_chunks)
            return c
        return None

def analyze_apple_maps(root, extractDeleted, extractSource):
    """
    解析苹果地图
    """
    maps = apple_maps(root, extractDeleted, extractSource)
    pr = ParserResults()
    pr.Models.AddRange(maps.analyze_maps_bookmarks())
    pr.Models.AddRange(maps.analyze_maps_history())
    return pr
    
def analyze_locations_from_deleted_photos(node, extractDeleted, extractSource):
    """
    从照片数据库中解析出地理位置信息,包括删除的照片及其记录
    """
    pr = ParserResults()
    if node is None:
        return pr
    db = SQLiteParser.Tools.GetDatabaseByPath(node, '', 'ZGENERICASSET')
    if db is None:
        return pr
    ## 这个函数只解析删除的记录(不删除的应该在照片那里处理,因为那样可以对应到具体的照片)
    if extractDeleted == False:
        return pr
    ts = SQLiteParser.TableSignature('ZGENERICASSET')
    SQLiteParser.Tools.AddSignatureToTable(ts, 'ZDATECREATED', SQLiteParser.Tools.SignatureType.Float)
    locs = []
    for rec in db.ReadTableRecords(ts, extractDeleted):
        trashedFile = False
        if "ZTRASHEDSTATE" in rec and not IsDBNull (rec["ZTRASHEDSTATE"].Value) and rec["ZTRASHEDSTATE"].Value == 1 and "ZTRASHEDDATE" in rec:
            trashedFile = True
        
        ## 这个函数只解析删除的记录(不删除的应该在照片那里处理,因为那样可以对应到具体的照片)
        if rec.Deleted == DeletedState.Intact and not trashedFile:
            continue
        
        if "ZFILENAME" not in rec or "ZDIRECTORY" not in rec or IsDBNull (rec["ZFILENAME"].Value) or IsDBNull (rec["ZDIRECTORY"].Value):
            continue

        ## 名字和目录
        zdir = rec["ZDIRECTORY"].Value
        name = rec["ZFILENAME"].Value

        if node.Parent.Parent != None:
            image_node = node.Parent.Parent.GetByPath(zdir + "/" + name)

            if image_node and "ZTRASHEDDATE" in rec and not IsDBNull (rec["ZTRASHEDDATE"].Value) and rec["ZTRASHEDDATE"].Value:
                try:
                    timestamp = TimeStamp(TimeStampFormats.GetTimeStampEpoch1Jan2001(rec["ZTRASHEDDATE"].Value), True)
                    image_node.DeletedTime = timestamp
                except:
                    pass

            if image_node and trashedFile:
                image_node.Deleted = DeletedState.Trash

        # 获取经纬度信息 
        if not IsDBNull (rec["ZLOCATIONDATA"].Value):
            ## 经纬度信息包含2个double
            buf = ''.join([chr(x) for x in rec["ZLOCATIONDATA"].Value])
            loc = Location()
            SQLiteParser.Tools.ReadColumnToField[TimeStamp](rec, 'ZDATECREATED', loc.TimeStamp, extractSource, ParserHelperTools.TryGetValidTimeStampEpoch1Jan2001)                    
            if extractSource:
                loc.TimeStamp.Source = MemoryRange (rec['ZDATECREATED'].Source)
            loc.Category.Value = LocationCategories.MEDIA;
            loc.Deleted = DeletedState.Deleted
            SQLiteParser.Tools.ReadColumnToField(rec, 'ZFILENAME', loc.Name, extractSource)
            if buf.startswith("bplist"):
                tree = BPReader.GetTree(MemoryRange(rec["ZLOCATIONDATA"].Source))
                cord = Coordinate()
                cord.Deleted = loc.Deleted
                if KNodeTools.TryReadToField(tree, "kCLLocationCodingKeyCoordinateLatitude", cord.Latitude) and \
                    KNodeTools.TryReadToField(tree, "kCLLocationCodingKeyCoordinateLongitude", cord.Latitude):
                    loc.Position.Value = cord
                    locs.Add(loc)
            else:    
                if len(buf) < 16:
                    continue
                (lat,lon) = struct.unpack ("<2d", buf[0:16])
                if (extractSource):
                    cord = Coordinate()
                    cord.Latitude.Init (lat, MemoryRange(rec['ZLOCATIONDATA'].Source))
                    cord.Longitude.Init (lon, MemoryRange(rec['ZLOCATIONDATA'].Source))
                else:
                    cord = Coordinate (lat, lon)
                loc.Position.Value=cord
                locs.Add(loc)

    pr.Models.AddRange(locs)
    return pr
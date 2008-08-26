""" 
olpc.datastore.datastore
~~~~~~~~~~~~~~~~~~~~~~~~
the datastore facade

""" 

__author__ = 'Benjamin Saller <bcsaller@objectrealms.net>'
__docformat__ = 'restructuredtext'
__copyright__ = 'Copyright ObjectRealms, LLC, 2007'
__license__  = 'The GNU Public License V2+'

import logging
import uuid
import time
import os

import dbus

from olpc.datastore import layoutmanager
from olpc.datastore.metadatastore import MetadataStore
from olpc.datastore.indexstore import IndexStore
from olpc.datastore.filestore import FileStore

# the name used by the logger
DS_LOG_CHANNEL = 'org.laptop.sugar.DataStore'

DS_SERVICE = "org.laptop.sugar.DataStore"
DS_DBUS_INTERFACE = "org.laptop.sugar.DataStore"
DS_OBJECT_PATH = "/org/laptop/sugar/DataStore"

logger = logging.getLogger(DS_LOG_CHANNEL)

class DataStore(dbus.service.Object):

    def __init__(self, **options):
        bus_name = dbus.service.BusName(DS_SERVICE,
                                        bus=dbus.SessionBus(),
                                        replace_existing=False,
                                        allow_replacement=False)
        dbus.service.Object.__init__(self, bus_name, DS_OBJECT_PATH)

        self._metadata_store = MetadataStore()
        self._index_store = IndexStore()
        self._file_store = FileStore()

    def _create_completion_cb(self, async_cb, async_err_cb, uid, exc=None):
        logger.debug("_create_completion_cb(%r, %r, %r, %r)" % \
            (async_cb, async_err_cb, uid, exc))
        if exc is not None:
            async_err_cb(exc)
            return

        self.Created(uid)
        logger.debug("created %s" % uid)
        async_cb(uid)

    @dbus.service.method(DS_DBUS_INTERFACE,
                         in_signature='a{sv}sb',
                         out_signature='s',
                         async_callbacks=('async_cb', 'async_err_cb'),
                         byte_arrays=True)
    def create(self, props, file_path, transfer_ownership,
               async_cb, async_err_cb):
        uid = str(uuid.uuid4())

        if not props.get('timestamp', ''):
            props['timestamp'] = int(time.time())

        self._metadata_store.store(uid, props)
        self._index_store.store(uid, props)
        self._file_store.store(uid, file_path, transfer_ownership,
                lambda *args: self._create_completion_cb(async_cb,
                                                         async_err_cb,
                                                         uid,
                                                         *args))

    @dbus.service.signal(DS_DBUS_INTERFACE, signature="s")
    def Created(self, uid):
        pass

    def _update_completion_cb(self, async_cb, async_err_cb, uid, exc=None):
        logger.debug("_update_completion_cb() called with %r / %r, exc %r" % \
            (async_cb, async_err_cb, exc))
        if exc is not None:
            async_err_cb(exc)
            return

        self.Updated(uid)
        logger.debug("updated %s" % uid)
        async_cb()

    @dbus.service.method(DS_DBUS_INTERFACE,
             in_signature='sa{sv}sb',
             out_signature='',
             async_callbacks=('async_cb', 'async_err_cb'),
             byte_arrays=True)
    def update(self, uid, props, file_path, transfer_ownership,
               async_cb, async_err_cb):
        if not props.get('timestamp', ''):
            props['timestamp'] = int(time.time())

        self._metadata_store.store(uid, props)
        self._index_store.store(uid, props)
        self._file_store.store(uid, file_path, transfer_ownership,
                lambda *args: self._update_completion_cb(async_cb,
                                                         async_err_cb,
                                                         uid,
                                                         *args))

    @dbus.service.signal(DS_DBUS_INTERFACE, signature="s")
    def Updated(self, uid):
        pass

    @dbus.service.method(DS_DBUS_INTERFACE,
             in_signature='a{sv}as',
             out_signature='aa{sv}u')
    def find(self, query, properties):
        t = time.time()
        uids, count = self._index_store.find(query)
        entries = []
        for uid in uids:
            metadata = self._metadata_store.retrieve(uid, properties)
            # Hack because the current journal expects the mountpoint property
            # to be present.
            metadata['mountpoint'] = '1'
            entries.append(metadata)
        logger.debug('find(): %r' % (time.time() - t))
        return entries, count

    @dbus.service.method(DS_DBUS_INTERFACE,
             in_signature='s',
             out_signature='s',
             sender_keyword='sender')
    def get_filename(self, uid, sender=None):
        user_id = dbus.Bus().get_unix_user(sender)
        return self._file_store.retrieve(uid, user_id)

    @dbus.service.method(DS_DBUS_INTERFACE,
                         in_signature='s',
                         out_signature='a{sv}')
    def get_properties(self, uid):
        metadata = self._metadata_store.retrieve(uid)
        # Hack because the current journal expects the mountpoint property to be
        # present.
        metadata['mountpoint'] = '1'
        return metadata

    @dbus.service.method(DS_DBUS_INTERFACE,
                         in_signature='sa{sv}',
                         out_signature='as')
    def get_uniquevaluesfor(self, propertyname, query=None):
        if propertyname != 'activity':
            raise ValueError('Only ''activity'' is a supported property name')
        if query:
            raise ValueError('The query parameter is not supported')
        return self._index_store.get_activities()

    @dbus.service.method(DS_DBUS_INTERFACE,
             in_signature='s',
             out_signature='')
    def delete(self, uid):
        self._index_store.delete(uid)
        self._file_store.delete(uid)
        self._metadata_store.delete(uid)
        
        entry_path = layoutmanager.get_instance().get_entry_path(uid)
        os.removedirs(entry_path)

        self.Deleted(uid)
        logger.debug("deleted %s" % uid)

    @dbus.service.signal(DS_DBUS_INTERFACE, signature="s")
    def Deleted(self, uid):
        pass

    def stop(self):
        """shutdown the service"""
        self.Stopped()

    @dbus.service.signal(DS_DBUS_INTERFACE)
    def Stopped(self):
        pass

    @dbus.service.method(DS_DBUS_INTERFACE,
                         in_signature="sa{sv}",
                         out_signature='s')
    def mount(self, uri, options=None):
        return ''

    @dbus.service.method(DS_DBUS_INTERFACE,
                         in_signature="",
                         out_signature="aa{sv}")
    def mounts(self):
        return [{'id': 1}]

    @dbus.service.method(DS_DBUS_INTERFACE,
                         in_signature="s",
                         out_signature="")
    def unmount(self, mountpoint_id):
        pass

    @dbus.service.signal(DS_DBUS_INTERFACE, signature="a{sv}")
    def Mounted(self, descriptior):
        pass

    @dbus.service.signal(DS_DBUS_INTERFACE, signature="a{sv}")
    def Unmounted(self, descriptor):
        pass


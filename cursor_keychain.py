"""Private reader helper: no UI, no refresh; bounded pipe back to its parent."""
import os
import sys

def keychain_token():
    """Read only an already-accessible item. SecItem forbids authentication UI.

    No `security -w`: that command can prompt to unlock/authorize the Keychain.
    No decrypt/refresh/write/interaction fallback. All native status is discarded.
    """
    import ctypes as c
    cf=c.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
    sec=c.CDLL('/System/Library/Frameworks/Security.framework/Security')
    pointer=c.c_void_p
    cf.CFStringCreateWithCString.argtypes=[pointer,c.c_char_p,c.c_uint32]
    cf.CFStringCreateWithCString.restype=pointer
    cf.CFDictionaryCreate.argtypes=[pointer,c.POINTER(pointer),c.POINTER(pointer),c.c_long,pointer,pointer]
    cf.CFDictionaryCreate.restype=pointer
    cf.CFRelease.argtypes=[pointer]
    cf.CFDataGetLength.argtypes=[pointer];cf.CFDataGetLength.restype=c.c_long
    cf.CFDataGetBytePtr.argtypes=[pointer];cf.CFDataGetBytePtr.restype=pointer
    sec.SecItemCopyMatching.argtypes=[pointer,c.POINTER(pointer)];sec.SecItemCopyMatching.restype=c.c_int32
    def constant(lib,name):return pointer.in_dll(lib,name).value
    strings=[];query=None;result=pointer()
    try:
        for value in (b'cursor-access-token',b'cursor-user'):
            ref=cf.CFStringCreateWithCString(None,value,0x08000100)
            if not ref:raise ValueError()
            strings.append(ref)
        keys=(pointer*5)(*[constant(sec,k) for k in ('kSecClass','kSecAttrService','kSecAttrAccount',
                                                    'kSecReturnData','kSecUseAuthenticationUI')])
        values=(pointer*5)(constant(sec,'kSecClassGenericPassword'),*strings,
                           constant(cf,'kCFBooleanTrue'),constant(sec,'kSecUseAuthenticationUIFail'))
        query=cf.CFDictionaryCreate(None,keys,values,5,None,None)
        if not query:raise ValueError()
        status=sec.SecItemCopyMatching(query,c.byref(result))
        if status==-25300:raise FileNotFoundError()
        if status!=0 or not result.value:raise ValueError()
        length=cf.CFDataGetLength(result)
        if not 0<length<=64*1024:raise ValueError()
        return c.string_at(cf.CFDataGetBytePtr(result),length).decode('utf-8')
    finally:
        if result.value:cf.CFRelease(result)
        if query:cf.CFRelease(query)
        for ref in strings:cf.CFRelease(ref)


if __name__=='__main__':
    try:
        value=keychain_token()
        sys.stdout.buffer.write(value.encode('utf-8'))
        sys.stdout.buffer.flush()
    except FileNotFoundError:os._exit(0)
    except BaseException:os._exit(4)

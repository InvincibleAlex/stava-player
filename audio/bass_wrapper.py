import os
import sys
import ctypes
import platform
SYSTEM_OS = platform.system()

# --- DEFINIȚII STRUCTURI BASS ---
class BASS_BFX_PEAKEQ(ctypes.Structure):
    _fields_ = [("lBand", ctypes.c_int), ("fBandwidth", ctypes.c_float),
                ("fQ", ctypes.c_float), ("fCenter", ctypes.c_float),
                ("fGain", ctypes.c_float), ("lChannel", ctypes.c_int)]

class BASS_BFX_COMPRESSOR2(ctypes.Structure):
    _fields_ = [("fGain", ctypes.c_float), ("fThreshold", ctypes.c_float),
                ("fRatio", ctypes.c_float), ("fAttack", ctypes.c_float),
                ("fRelease", ctypes.c_float), ("lChannel", ctypes.c_int)]

class BASS_BFX_REVERB(ctypes.Structure):
    # Legacy BASS_FX Reverb
    _fields_ = [("fLevel", ctypes.c_float), ("lDelay", ctypes.c_int)]

class BASS_BFX_FREEVERB(ctypes.Structure):
    # Freeverb (Modern Reverb algorithm)
    _fields_ = [("fDryMix", ctypes.c_float), ("fWetMix", ctypes.c_float),
                ("fRoomSize", ctypes.c_float), ("fDamp", ctypes.c_float),
                ("fWidth", ctypes.c_float), ("lMode", ctypes.c_uint32),
                ("lChannel", ctypes.c_int)]

class BASS_BFX_CHORUS(ctypes.Structure):
    _fields_ = [("fDryMix", ctypes.c_float), ("fWetMix", ctypes.c_float),
                ("fFeedback", ctypes.c_float), ("fMinSweep", ctypes.c_float),
                ("fMaxSweep", ctypes.c_float), ("fRate", ctypes.c_float),
                ("lChannel", ctypes.c_int)]

class BASS_CHANNELINFO(ctypes.Structure):
    _fields_ = [("freq", ctypes.c_uint32), ("chans", ctypes.c_uint32),
                ("flags", ctypes.c_uint32), ("ctype", ctypes.c_uint32),
                ("origres", ctypes.c_uint32), ("plugin", ctypes.c_uint32),
                ("sample", ctypes.c_uint32), ("filename", ctypes.c_char_p)]

class BASS_BFX_BQF(ctypes.Structure):
    _fields_ = [
        ("lFilter", ctypes.c_int),
        ("fCenter", ctypes.c_float),
        ("fGain", ctypes.c_float),
        ("fBandwidth", ctypes.c_float),
        ("fQ", ctypes.c_float),
        ("fS", ctypes.c_float),
        ("lChannel", ctypes.c_int),
    ]

# --- CONSTANTE BASS ---
BASS_ATTRIB_TEMPO = 0x10000
BASS_ATTRIB_PAN = 3
BASS_FX_BFX_PEAKEQ = 0x10004
BASS_FX_BFX_REVERB = 0x10005
BASS_FX_BFX_CHORUS = 0x1000D
BASS_FX_BFX_COMPRESSOR2 = 0x10011
BASS_FX_BFX_BQF = 0x10013
BASS_FX_BFX_FREEVERB = 0x10016
BASS_FX_FREESOURCE = 0x10000 
BASS_ATTRIB_VOL = 2
BASS_STREAM_DECODE = 0x200000
BASS_SAMPLE_FLOAT = 256
BASS_SAMPLE_MONO = 2
BASS_DATA_FLOAT = 0x40000000
BASS_DATA_FFT256 = 0x80000000  # Returnează 128 de float-uri
BASS_UNICODE = 0x80000000  # Windows expects UTF-16LE, macOS/Linux expect UTF-8 when this flag is set

BASS_BFX_BQF_LOWPASS = 0
BASS_BFX_BQF_HIGHPASS = 1
BASS_BFX_BQF_BANDPASS = 2
BASS_BFX_BQF_BANDPASS_Q = 3
BASS_BFX_BQF_NOTCH = 4
BASS_BFX_BQF_ALLPASS = 5
BASS_BFX_BQF_PEAKINGEQ = 6
BASS_BFX_BQF_LOWSHELF = 7
BASS_BFX_BQF_HIGHSHELF = 8

class BassLoader:
    @staticmethod
    def load_libraries():
        """ Încarcă bibliotecile BASS și returnează obiectele CDLL """
        system_os = platform.system()
        # Presupunem că libs sunt în folderul 'libs' relativ la acest fișier
        
        # 🔥 FIX: Detectare cale corectă pentru PyInstaller (Frozen) vs Dev
        if getattr(sys, 'frozen', False):
            if hasattr(sys, '_MEIPASS'):
                root_dir = sys._MEIPASS # --onefile
            else:
                # --onedir (macOS .app): sys.executable este în Contents/MacOS/
                root_dir = os.path.dirname(os.path.abspath(sys.executable))
        else:
            # Dev mode: fișierul e în /audio, dar libs e în rădăcina proiectului
            this_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(this_dir)
            root_dir = project_root if os.path.exists(os.path.join(project_root, 'libs')) else this_dir
            
        libs_dir = os.path.join(root_dir, 'libs')

        if not os.path.exists(libs_dir):
            print(f"!!! EROARE CRITICĂ: Folderul '{libs_dir}' nu există!")
            sys.exit(1)

        if system_os == 'Darwin': # macOS
            lib_bass = os.path.join(libs_dir, 'libbass.dylib')
            lib_fx = os.path.join(libs_dir, 'libbass_fx.dylib')
            lib_flac = os.path.join(libs_dir, 'libbassflac.dylib')
            lib_vst = os.path.join(libs_dir, 'libbass_vst.dylib')
        elif system_os == 'Windows': # Windows
            lib_bass = os.path.join(libs_dir, 'bass.dll')
            lib_fx = os.path.join(libs_dir, 'bass_fx.dll')
            lib_flac = os.path.join(libs_dir, 'bassflac.dll')
            lib_vst = os.path.join(libs_dir, 'bass_vst.dll')
        else: # Linux
            lib_bass = os.path.join(libs_dir, 'libbass.so')
            lib_fx = os.path.join(libs_dir, 'libbass_fx.so')
            lib_flac = os.path.join(libs_dir, 'libbassflac.so')
            lib_vst = os.path.join(libs_dir, 'libbass_vst.so')

        try:
            if not os.path.exists(lib_bass):
                raise OSError(f"Nu găsesc fișierul principal: {lib_bass}")

            # Pe Windows folosim WinDLL (stdcall), pe restul CDLL (cdecl)
            if system_os == 'Windows':
                bass = ctypes.WinDLL(lib_bass)
                bass_fx = ctypes.WinDLL(lib_fx)
                bass_vst = None
                if os.path.exists(lib_vst):
                    bass_vst = ctypes.WinDLL(lib_vst)
                else:
                    print(f"ATENȚIE: Lipsă libbass_vst ({lib_vst}).")
            else:
                # Load base lib with RTLD_GLOBAL so dependent FX libraries can resolve symbols
                try:
                    bass = ctypes.CDLL(lib_bass, mode=ctypes.RTLD_GLOBAL)
                except Exception:
                    bass = ctypes.CDLL(lib_bass)
                bass_fx = ctypes.CDLL(lib_fx)
                bass_vst = None
                if os.path.exists(lib_vst):
                    try:
                        bass_vst = ctypes.CDLL(lib_vst)
                    except Exception:
                        bass_vst = None
                        print(f"ATENȚIE: Nu pot încărca libbass_vst ({lib_vst}).")
                else:
                    print(f"ATENȚIE: Lipsă libbass_vst ({lib_vst}).")
            
            # Setup Prototypes
            BassLoader._setup_prototypes(bass, bass_fx, bass_vst)

            # --- RUNTIME PROBE: Print library info and symbol availability ---
            try:
                print(f"DEBUG BASS PROBE: lib_bass={lib_bass} lib_fx={lib_fx} loaded_for={platform.machine()}")
                def _addr(obj, name):
                    try:
                        if hasattr(obj, name):
                            ptr = getattr(obj, name)
                            try:
                                addr = ctypes.cast(ptr, ctypes.c_void_p).value
                                return addr
                            except Exception:
                                # fallback: try accessing .value if available
                                try:
                                    return ptr.value
                                except Exception:
                                    return None
                        return None
                    except Exception:
                        return None

                for sym in ("BASS_FXSetParameters", "BASS_FXGetParameters", "BASS_FX_TempoCreate"):
                    present = hasattr(bass_fx, sym)
                    addr = _addr(bass_fx, sym) if present else None
                    print(f"DEBUG BASS PROBE: {sym} present={present} addr={addr}")

                for sym in ("BASS_Init", "BASS_ChannelSetFX", "BASS_ChannelGetInfo"):
                    present = hasattr(bass, sym)
                    addr = _addr(bass, sym) if present else None
                    print(f"DEBUG BASS PROBE: {sym} present={present} addr={addr}")
            except Exception as e:
                print(f"DEBUG BASS PROBE: probe failed: {e}")
            
            # Init BASS
            if not bass.BASS_Init(-1, 48000, 0, None, None):
                err = bass.BASS_ErrorGetCode()
                # 14 = BASS_ERROR_ALREADY (Ignorăm dacă e deja inițializat)
                if err != 14:
                    print(f"BASS_Init error: {err}")

            # Load FLAC Plugin
            if os.path.exists(lib_flac):
                plugin_path_bytes = lib_flac.encode('utf-8')
                bass.BASS_PluginLoad(plugin_path_bytes, 0)
            
            return bass, bass_fx, bass_vst

        except OSError as e:
            if "WinError 193" in str(e) and system_os == 'Windows':
                is_64bits = sys.maxsize > 2**32
                arch = "64-bit" if is_64bits else "32-bit"
                print(f"\n!!! EROARE CRITICĂ DLL: Arhitectură incompatibilă (WinError 193).")
                print(f"Python rulează pe {arch}, dar fișierele .dll din 'libs' sunt pentru cealaltă arhitectură.")
                print(f"SOLUȚIE: Înlocuiește fișierele din 'libs' cu versiunea {arch} a bibliotecilor BASS.")
                print(f"Notă: În arhiva BASS descărcată, versiunea 64-bit este de obicei în folderul 'x64'.\n")
            else:
                print(f"AUDIO ENGINE ERROR: {e}")
            sys.exit(1)

    @staticmethod
    def _setup_prototypes(bass, bass_fx, bass_vst):
        def bind_symbol(preferred_lib, fallback_lib, name):
            for lib in (preferred_lib, fallback_lib):
                if lib is None:
                    continue
                try:
                    func = getattr(lib, name)
                    if preferred_lib is not None and lib is not preferred_lib:
                        setattr(preferred_lib, name, func)
                    return func
                except AttributeError:
                    continue
            raise AttributeError(f"function '{name}' not found in provided BASS libraries")

        # System Prototypes
        bass.BASS_Init.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p]
        bass.BASS_Init.restype = ctypes.c_bool
        
        bass.BASS_Free.argtypes = []
        bass.BASS_Free.restype = ctypes.c_bool
        
        bass.BASS_ErrorGetCode.argtypes = []
        bass.BASS_ErrorGetCode.restype = ctypes.c_int

        bass.BASS_GetVersion.argtypes = []
        bass.BASS_GetVersion.restype = ctypes.c_uint32

        bass.BASS_StreamCreateFile.argtypes = [ctypes.c_bool, ctypes.c_char_p, ctypes.c_ulonglong, ctypes.c_ulonglong, ctypes.c_ulong]
        bass.BASS_StreamCreateFile.restype = ctypes.c_ulong

        fx_set_parameters = bind_symbol(bass_fx, bass, 'BASS_FXSetParameters')
        fx_get_parameters = bind_symbol(bass_fx, bass, 'BASS_FXGetParameters')
        fx_tempo_create = bind_symbol(bass_fx, bass, 'BASS_FX_TempoCreate')
        
        bass.BASS_ChannelPlay.argtypes = [ctypes.c_ulong, ctypes.c_bool]
        bass.BASS_ChannelStart.argtypes = [ctypes.c_ulong]
        bass.BASS_ChannelStart.restype = ctypes.c_bool
        bass.BASS_ChannelSetAttribute.argtypes = [ctypes.c_ulong, ctypes.c_ulong, ctypes.c_float]
        bass.BASS_ChannelSetFX.argtypes = [ctypes.c_ulong, ctypes.c_ulong, ctypes.c_int]
        bass.BASS_ChannelSetFX.restype = ctypes.c_ulong
        fx_set_parameters.argtypes = [ctypes.c_ulong, ctypes.c_void_p]
        fx_set_parameters.restype = ctypes.c_bool
        fx_get_parameters.argtypes = [ctypes.c_ulong, ctypes.c_void_p]
        fx_get_parameters.restype = ctypes.c_bool
        
        bass.BASS_ChannelGetInfo.argtypes = [ctypes.c_ulong, ctypes.c_void_p]
        bass.BASS_ChannelGetInfo.restype = ctypes.c_bool
        
        fx_tempo_create.argtypes = [ctypes.c_ulong, ctypes.c_ulong]
        fx_tempo_create.restype = ctypes.c_ulong

        bass.BASS_ChannelBytes2Seconds.argtypes = [ctypes.c_ulong, ctypes.c_ulonglong]
        bass.BASS_ChannelBytes2Seconds.restype = ctypes.c_double
        
        bass.BASS_ChannelSeconds2Bytes.argtypes = [ctypes.c_ulong, ctypes.c_double]
        bass.BASS_ChannelSeconds2Bytes.restype = ctypes.c_ulonglong
        
        bass.BASS_ChannelGetPosition.argtypes = [ctypes.c_ulong, ctypes.c_int]
        bass.BASS_ChannelGetPosition.restype = ctypes.c_ulonglong
        
        bass.BASS_ChannelSetPosition.argtypes = [ctypes.c_ulong, ctypes.c_ulonglong, ctypes.c_int]
        
        bass.BASS_ChannelGetLength.argtypes = [ctypes.c_ulong, ctypes.c_int]
        bass.BASS_ChannelGetLength.restype = ctypes.c_ulonglong
        
        bass.BASS_ChannelRemoveFX.argtypes = [ctypes.c_ulong, ctypes.c_ulong]
        
        bass.BASS_PluginLoad.argtypes = [ctypes.c_char_p, ctypes.c_ulong]
        bass.BASS_PluginLoad.restype = ctypes.c_ulong
        
        bass.BASS_ChannelGetData.argtypes = [ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong]
        bass.BASS_ChannelGetData.restype = ctypes.c_ulong

        bass.BASS_Set3DFactors.argtypes = [ctypes.c_float, ctypes.c_float, ctypes.c_float]
        bass.BASS_Set3DFactors.restype = ctypes.c_bool

        bass.BASS_Set3DPosition.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        bass.BASS_Set3DPosition.restype = ctypes.c_bool

        bass.BASS_Apply3D.argtypes = []
        bass.BASS_Apply3D.restype = ctypes.c_bool

        bass.BASS_ChannelSet3DAttributes.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_float, ctypes.c_float,
                                  ctypes.c_int, ctypes.c_int, ctypes.c_float]
        bass.BASS_ChannelSet3DAttributes.restype = ctypes.c_bool

        bass.BASS_ChannelSet3DPosition.argtypes = [ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        bass.BASS_ChannelSet3DPosition.restype = ctypes.c_bool
        
        if bass_vst:
            bass_vst.BASS_VST_ChannelSetDSP.argtypes = [ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int]
            bass_vst.BASS_VST_ChannelSetDSP.restype = ctypes.c_ulong
            bass_vst.BASS_VST_SetParam.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_float]
            if hasattr(bass_vst, 'BASS_VST_SetBypass'):
                bass_vst.BASS_VST_SetBypass.argtypes = [ctypes.c_ulong, ctypes.c_bool]
                bass_vst.BASS_VST_SetBypass.restype = ctypes.c_bool
            if hasattr(bass_vst, 'BASS_VST_EmbedEditor'):
                bass_vst.BASS_VST_EmbedEditor.argtypes = [ctypes.c_ulong, ctypes.c_void_p]
                bass_vst.BASS_VST_EmbedEditor.restype = ctypes.c_bool
        
        bass.BASS_StreamFree.argtypes = [ctypes.c_ulong]

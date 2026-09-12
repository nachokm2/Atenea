/// Utilidades compartidas por las pruebas de Atenea.
///
/// El objetivo es montar las piezas reales —los mismos controladores, el mismo
/// enrutador y el mismo tema— sin tocar la red ni el almacenamiento del
/// dispositivo.
library;

import 'package:atenea/data/almacen_tokens.dart';
import 'package:atenea/data/api_client.dart';
import 'package:atenea/datos/repositorios.dart';
import 'package:google_fonts/google_fonts.dart';

/// Almacén de tokens que no toca el llavero del sistema.
///
/// [AlmacenTokens] usa `flutter_secure_storage`, que en una prueba de widget
/// no tiene implementación de plataforma. Esta versión guarda en memoria y
/// permite arrancar la sesión con tokens o sin ellos.
class AlmacenTokensFalso extends AlmacenTokens {
  AlmacenTokensFalso({String? acceso, String? refresco})
      : _acceso = acceso,
        _refresco = refresco;

  String? _acceso;
  String? _refresco;

  @override
  Future<void> cargar() async {}

  @override
  String? get acceso => _acceso;

  @override
  String? get refresco => _refresco;

  @override
  bool get haySesion => (_acceso ?? '').isNotEmpty;

  @override
  Future<void> guardar({
    required String acceso,
    required String refresco,
  }) async {
    _acceso = acceso;
    _refresco = refresco;
  }

  @override
  Future<void> actualizarAcceso(String acceso) async => _acceso = acceso;

  @override
  Future<void> limpiar() async {
    _acceso = null;
    _refresco = null;
  }
}

/// Repositorios sobre una URL que no existe.
///
/// Ninguna prueba debe llegar a hacer una petición; si alguna lo intentara,
/// fallaría de forma evidente en vez de alcanzar un servidor real.
Repositorios repositoriosDePrueba(AlmacenTokens tokens) => Repositorios(
      ApiClient(baseUrl: 'http://pruebas.invalido/api/v1', tokens: tokens),
    );

/// Evita que `google_fonts` descargue tipografías durante las pruebas.
///
/// Sin esto cada prueba dispara peticiones HTTP que el entorno de pruebas
/// rechaza. Con esto la familia cae a la tipografía por defecto —el paquete
/// registra el aviso y sigue— y la maquetación se mide igual.
void prepararTipografias() {
  GoogleFonts.config.allowRuntimeFetching = false;
}

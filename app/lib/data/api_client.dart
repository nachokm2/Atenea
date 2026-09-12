import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

import 'almacen_tokens.dart';
import 'errores.dart';

/// Cliente HTTP de Atenea.
///
/// Responsabilidades:
/// - Añadir el token de acceso a cada petición.
/// - Refrescar el token una sola vez cuando la API responde 401, poniendo en
///   cola las peticiones que llegan mientras dura el refresco.
/// - Traducir cualquier fallo a [ErrorAtenea], con mensaje en español.
/// - Enviar la zona horaria del dispositivo, que el backend necesita para
///   calcular correctamente el día de la racha.
class ApiClient {
  ApiClient({
    required this.baseUrl,
    required AlmacenTokens tokens,
    Dio? dio,
    this.alPerderSesion,
    this.zonaHorariaIana,
  })  : _tokens = tokens,
        _dio = dio ?? Dio() {
    _dio.options = _dio.options.copyWith(
      baseUrl: baseUrl,
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 60),
      sendTimeout: const Duration(seconds: 60),
      headers: <String, dynamic>{'Accept': 'application/json'},
      // Dejamos pasar cualquier código: el manejo de errores es nuestro.
      validateStatus: (int? c) => c != null && c < 500,
    );
    _dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: _alEnviar,
        onError: _alFallar,
      ),
    );
    if (kDebugMode) {
      _dio.interceptors.add(
        LogInterceptor(requestBody: false, responseBody: false, request: false),
      );
    }
  }

  /// URL base de la API, por ejemplo `http://localhost:8000/api/v1`.
  final String baseUrl;

  /// Se invoca cuando el refresco falla y hay que volver a la pantalla de
  /// acceso.
  final VoidCallback? alPerderSesion;

  /// Zona horaria IANA del usuario (`America/Santiago`), si se conoce.
  ///
  /// Se rellena en cuanto llegan los ajustes del perfil y desde entonces manda
  /// sobre lo que diga el sistema. Mientras siga nula se intenta deducir del
  /// sistema, y si eso tampoco da una zona válida no se envía nada: el Reino
  /// prefiere su propio dato guardado antes que una adivinanza.
  String? zonaHorariaIana;

  final Dio _dio;
  final AlmacenTokens _tokens;

  /// Refresco en curso, compartido por todas las peticiones que fallen con 401
  /// al mismo tiempo.
  Future<bool>? _refrescoEnCurso;

  Dio get bruto => _dio;

  Future<void> _alEnviar(RequestOptions opciones, RequestInterceptorHandler handler) async {
    await _tokens.cargar();
    final String? token = _tokens.acceso;
    if (token != null && token.isNotEmpty && opciones.extra['sinAuth'] != true) {
      opciones.headers['Authorization'] = 'Bearer $token';
    }
    // El nombre de la cabecera es el del contrato (§8.4), no una traducción:
    // el Reino lee `X-Timezone` y con eso decide de qué día es cada actividad.
    final String? zona = zonaHorariaIana ?? zonaDelSistema();
    if (zona != null) opciones.headers['X-Timezone'] ??= zona;
    opciones.headers['X-Timezone-Offset'] ??= DateTime.now().timeZoneOffset.inMinutes;
    handler.next(opciones);
  }

  /// Zona horaria del sistema, **solo si** es una identificación IANA válida.
  ///
  /// `DateTime.timeZoneName` devuelve lo que cada sistema quiera: en Linux suele
  /// ser `America/Santiago`, pero en un Windows en español devuelve "Hora verano
  /// Sudamérica Pacífico", con acento y espacios. Una cabecera HTTP solo admite
  /// ASCII, así que enviar eso hacía que el servidor respondiera 400 a **todas**
  /// las peticiones: la app no funcionaba en absoluto en esas máquinas.
  ///
  /// Ante la duda se omite: el Reino ya guarda la zona del usuario en su perfil
  /// y prefiere esa antes que una adivinanza.
  static String? zonaDelSistema() {
    final String nombre = DateTime.now().timeZoneName.trim();
    return _ianaValida.hasMatch(nombre) ? nombre : null;
  }

  /// `Region/Ciudad`, solo ASCII, como manda la base de datos de zonas IANA.
  static final RegExp _ianaValida =
      RegExp(r'^[A-Za-z][A-Za-z0-9_+-]*(?:/[A-Za-z0-9_+-]+)+$');

  Future<void> _alFallar(DioException e, ErrorInterceptorHandler handler) async {
    handler.next(e);
  }

  /// Ejecuta una petición y devuelve el cuerpo ya decodificado.
  ///
  /// Si la respuesta es 401 y hay token de refresco, lo renueva y reintenta
  /// una vez.
  Future<T> _pedir<T>(
    String metodo,
    String ruta, {
    Object? cuerpo,
    Map<String, dynamic>? consulta,
    String? claveIdempotencia,
    bool sinAuth = false,
    bool esReintento = false,
    Duration? tiempoLimite,
  }) async {
    try {
      final Response<dynamic> r = await _dio.request<dynamic>(
        ruta,
        data: cuerpo,
        queryParameters: consulta,
        options: Options(
          method: metodo,
          extra: <String, dynamic>{'sinAuth': sinAuth},
          receiveTimeout: tiempoLimite,
          headers: <String, dynamic>{
            'Idempotency-Key': ?claveIdempotencia,
          },
        ),
      );

      final int estado = r.statusCode ?? 0;
      if (estado == 401 && !sinAuth && !esReintento) {
        final bool renovado = await _refrescar();
        if (renovado) {
          return _pedir<T>(
            metodo,
            ruta,
            cuerpo: cuerpo,
            consulta: consulta,
            claveIdempotencia: claveIdempotencia,
            esReintento: true,
            tiempoLimite: tiempoLimite,
          );
        }
        await _tokens.limpiar();
        alPerderSesion?.call();
      }

      if (estado >= 400) {
        throw ErrorAtenea.desdeDio(
          DioException(
            requestOptions: r.requestOptions,
            response: r,
            type: DioExceptionType.badResponse,
          ),
        );
      }

      return r.data as T;
    } on DioException catch (e) {
      throw ErrorAtenea.desdeDio(e);
    }
  }

  /// Renueva el token de acceso. Un único refresco simultáneo para todas las
  /// peticiones en vuelo.
  Future<bool> _refrescar() {
    return _refrescoEnCurso ??= _hacerRefresco().whenComplete(() {
      _refrescoEnCurso = null;
    });
  }

  Future<bool> _hacerRefresco() async {
    final String? refresco = _tokens.refresco;
    if (refresco == null || refresco.isEmpty) return false;
    try {
      final Response<dynamic> r = await _dio.post<dynamic>(
        '/auth/refresh',
        data: <String, dynamic>{'refresh_token': refresco},
        options: Options(extra: <String, dynamic>{'sinAuth': true}),
      );
      if ((r.statusCode ?? 0) >= 400 || r.data is! Map) return false;
      final Map<String, dynamic> datos = Map<String, dynamic>.from(r.data as Map);
      final String? nuevoAcceso = (datos['access_token'] ?? datos['acceso']) as String?;
      final String? nuevoRefresco = (datos['refresh_token'] ?? datos['refresco']) as String?;
      if (nuevoAcceso == null) return false;
      if (nuevoRefresco != null) {
        await _tokens.guardar(acceso: nuevoAcceso, refresco: nuevoRefresco);
      } else {
        await _tokens.actualizarAcceso(nuevoAcceso);
      }
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<Map<String, dynamic>> obtener(
    String ruta, {
    Map<String, dynamic>? consulta,
    bool sinAuth = false,
  }) async {
    final dynamic d = await _pedir<dynamic>('GET', ruta, consulta: consulta, sinAuth: sinAuth);
    return _comoMapa(d);
  }

  Future<List<dynamic>> obtenerLista(
    String ruta, {
    Map<String, dynamic>? consulta,
    bool sinAuth = false,
  }) async {
    final dynamic d = await _pedir<dynamic>('GET', ruta, consulta: consulta, sinAuth: sinAuth);
    if (d is List) return d;
    if (d is Map && d['items'] is List) return d['items'] as List<dynamic>;
    if (d is Map && d['datos'] is List) return d['datos'] as List<dynamic>;
    return const <dynamic>[];
  }

  Future<Map<String, dynamic>> enviar(
    String ruta, {
    Object? cuerpo,
    Map<String, dynamic>? consulta,
    String? claveIdempotencia,
    bool sinAuth = false,
    Duration? tiempoLimite,
  }) async {
    final dynamic d = await _pedir<dynamic>(
      'POST',
      ruta,
      cuerpo: cuerpo,
      consulta: consulta,
      claveIdempotencia: claveIdempotencia,
      sinAuth: sinAuth,
      tiempoLimite: tiempoLimite,
    );
    return _comoMapa(d);
  }

  Future<Map<String, dynamic>> actualizar(
    String ruta, {
    Object? cuerpo,
    bool parcial = true,
  }) async {
    final dynamic d = await _pedir<dynamic>(parcial ? 'PATCH' : 'PUT', ruta, cuerpo: cuerpo);
    return _comoMapa(d);
  }

  Future<void> eliminar(String ruta) async {
    await _pedir<dynamic>('DELETE', ruta);
  }

  /// Sube un archivo (documento de estudio) con multipart.
  Future<Map<String, dynamic>> subirArchivo(
    String ruta, {
    required List<int> bytes,
    required String nombreArchivo,
    Map<String, dynamic>? campos,
    ProgressCallback? alProgresar,
  }) async {
    try {
      final FormData formulario = FormData.fromMap(<String, dynamic>{
        ...?campos,
        'file': MultipartFile.fromBytes(bytes, filename: nombreArchivo),
      });
      await _tokens.cargar();
      final Response<dynamic> r = await _dio.post<dynamic>(
        ruta,
        data: formulario,
        onSendProgress: alProgresar,
        options: Options(sendTimeout: const Duration(minutes: 5)),
      );
      if ((r.statusCode ?? 0) >= 400) {
        throw ErrorAtenea.desdeDio(
          DioException(
            requestOptions: r.requestOptions,
            response: r,
            type: DioExceptionType.badResponse,
          ),
        );
      }
      return _comoMapa(r.data);
    } on DioException catch (e) {
      throw ErrorAtenea.desdeDio(e);
    }
  }

  static Map<String, dynamic> _comoMapa(dynamic d) {
    if (d is Map) return Map<String, dynamic>.from(d);
    if (d == null || (d is String && d.isEmpty)) return <String, dynamic>{};
    return <String, dynamic>{'datos': d};
  }
}

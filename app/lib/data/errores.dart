import 'package:dio/dio.dart';

/// Error de dominio de la aplicación, ya traducido a español y listo para
/// mostrarse en la interfaz.
///
/// La API devuelve los errores con la forma `{"error": {"code", "message",
/// "details"}}`. El intérprete es tolerante y también entiende la forma plana
/// y el `detail` propio de FastAPI, para que un cambio menor en el backend no
/// deje al usuario sin mensaje.
class ErrorAtenea implements Exception {
  const ErrorAtenea({
    required this.codigo,
    required this.mensaje,
    this.detalles,
    this.estadoHttp,
  });

  /// Código estable, por ejemplo `credenciales_invalidas` o `cuota_agotada`.
  final String codigo;

  /// Mensaje en español, apto para mostrar tal cual.
  final String mensaje;

  /// Información adicional (por ejemplo, errores por campo).
  final Map<String, dynamic>? detalles;

  final int? estadoHttp;

  /// ¿Conviene ofrecer un botón de reintento?
  bool get esReintentable =>
      estadoHttp == null || estadoHttp! >= 500 || estadoHttp == 408 || estadoHttp == 429;

  /// La sesión caducó y hay que volver a autenticarse.
  bool get requiereReautenticar => estadoHttp == 401;

  /// Se acabó la cuota del plan gratuito.
  bool get esCuotaAgotada => estadoHttp == 402 || codigo.contains('cuota');

  @override
  String toString() => 'ErrorAtenea($codigo, $estadoHttp): $mensaje';

  /// Traduce cualquier fallo de Dio a un error de dominio con mensaje humano.
  factory ErrorAtenea.desdeDio(DioException e) {
    final Response<dynamic>? r = e.response;
    final int? estado = r?.statusCode;

    if (e.type == DioExceptionType.connectionTimeout ||
        e.type == DioExceptionType.receiveTimeout ||
        e.type == DioExceptionType.sendTimeout) {
      return const ErrorAtenea(
        codigo: 'tiempo_agotado',
        mensaje: 'El Reino tardó demasiado en responder. Revisa tu conexión e inténtalo otra vez.',
      );
    }

    if (e.type == DioExceptionType.connectionError || e.type == DioExceptionType.unknown) {
      return const ErrorAtenea(
        codigo: 'sin_conexion',
        mensaje: 'Sin conexión con el Reino. Comprueba tu red e inténtalo de nuevo.',
      );
    }

    if (e.type == DioExceptionType.cancel) {
      return const ErrorAtenea(codigo: 'cancelado', mensaje: 'Operación cancelada.');
    }

    final dynamic cuerpo = r?.data;
    if (cuerpo is Map) {
      final Map<String, dynamic> mapa = Map<String, dynamic>.from(cuerpo);

      // Forma canónica: {"error": {...}}
      final dynamic anidado = mapa['error'];
      if (anidado is Map) {
        final Map<String, dynamic> err = Map<String, dynamic>.from(anidado);
        return ErrorAtenea(
          codigo: (err['code'] ?? err['codigo'] ?? 'error').toString(),
          mensaje: (err['message'] ?? err['mensaje'] ?? _porEstado(estado)).toString(),
          detalles: _detallesDe(err),
          estadoHttp: estado,
        );
      }

      // Forma plana: {"code": ..., "message": ...}
      if (mapa.containsKey('message') || mapa.containsKey('code')) {
        return ErrorAtenea(
          codigo: (mapa['code'] ?? 'error').toString(),
          mensaje: (mapa['message'] ?? _porEstado(estado)).toString(),
          detalles: _detallesDe(mapa),
          estadoHttp: estado,
        );
      }

      // Forma de FastAPI: {"detail": "..."} o {"detail": [ ... ]}
      final dynamic detalle = mapa['detail'];
      if (detalle is String) {
        return ErrorAtenea(codigo: 'error', mensaje: detalle, estadoHttp: estado);
      }
      if (detalle is List && detalle.isNotEmpty) {
        final dynamic primero = detalle.first;
        final String msg = primero is Map && primero['msg'] != null
            ? primero['msg'].toString()
            : _porEstado(estado);
        return ErrorAtenea(
          codigo: 'validacion',
          mensaje: msg,
          detalles: <String, dynamic>{'errores': detalle},
          estadoHttp: estado,
        );
      }
    }

    return ErrorAtenea(codigo: 'error', mensaje: _porEstado(estado), estadoHttp: estado);
  }

  /// Junta `details` y `field_errors`, que el Reino manda **hermanos**.
  ///
  /// El sobre es `{"error": {"message": …, "details": {…}, "field_errors": […]}}`
  /// y aquí se guardaba solo `details`. Pero `details` viene casi siempre vacío
  /// y lo útil está en `field_errors`: al registrarse con una contraseña floja,
  /// `message` dice «Esa contraseña es demasiado débil» y `field_errors` dice
  /// **qué le falta** —«Debe incluir una letra mayúscula», «Debe incluir un
  /// número»—. Sin esto el aprendiz lee que algo está mal y no puede saber qué,
  /// que es tanto como no poder registrarse.
  ///
  /// Las pantallas ya lo buscaban dentro de `detalles['field_errors']`: la
  /// mitad que faltaba era esta, ponerlo ahí.
  static Map<String, dynamic>? _detallesDe(Map<String, dynamic> err) {
    final Map<String, dynamic> junto = <String, dynamic>{
      if (err['details'] is Map) ...Map<String, dynamic>.from(err['details'] as Map),
      if (err['field_errors'] is List) 'field_errors': err['field_errors'],
    };
    return junto.isEmpty ? null : junto;
  }

  static String _porEstado(int? estado) => switch (estado) {
        400 => 'La solicitud no es válida.',
        401 => 'Tu sesión expiró. Vuelve a entrar al Reino.',
        403 => 'No tienes acceso a esta parte del Reino.',
        404 => 'No encontramos lo que buscabas.',
        409 => 'Ese dato ya existe.',
        413 => 'El archivo es demasiado grande.',
        422 => 'Revisa los datos ingresados.',
        429 => 'Demasiadas peticiones seguidas. Espera un momento.',
        _ when estado != null && estado >= 500 =>
          'El Reino tiene problemas en este momento. Inténtalo en unos minutos.',
        _ => 'Ocurrió un error inesperado.',
      };
}

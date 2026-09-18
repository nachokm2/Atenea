@Tags(<String>['vivo'])
library;

import 'dart:convert';
import 'dart:io';

import 'package:atenea/nucleo/entorno.dart';
import 'package:flutter_test/flutter_test.dart';

/// La URL de producción tiene que existir.
///
/// Parece de perogrullo y no lo es: durante meses `Entorno.apiProduccion` apuntó
/// a `https://api.atenea.cl/api/v1`, que **no existe**. El dominio `atenea.cl`
/// está registrado por otra empresa y no hay tal subdominio, así que cualquier
/// compilación de release sin `--dart-define=ATENEA_API` salía sin servidor: la
/// aplicación abría, se veía entera, y no cargaba un solo dato.
///
/// Ninguna de las ciento cincuenta pruebas lo vio, y no por descuido: ninguna
/// sale a la red, y esto **solo** se ve saliendo. Una constante con una URL
/// dentro no se puede verificar leyéndola; hay que llamarla.
///
/// Se salta si no hay red, como las de contrato vivo, para no romper una
/// ejecución normal de `flutter test`. Que se salte no es gratis —si se salta
/// siempre, no protege de nada— así que conviene correrla a conciencia antes de
/// publicar:
///
///     flutter test test/produccion_existe_test.dart
void main() {
  test('el servidor de producción responde y está sano', () async {
    final Uri salud = Uri.parse('${Entorno.apiProduccion}/health');
    final HttpClient cliente = HttpClient()
      ..connectionTimeout = const Duration(seconds: 12);

    int codigo;
    String cuerpo;
    try {
      final HttpClientRequest peticion = await cliente.getUrl(salud);
      final HttpClientResponse respuesta =
          await peticion.close().timeout(const Duration(seconds: 20));
      codigo = respuesta.statusCode;
      // El cuerpo se lee **antes** de cerrar el cliente: cerrarlo corta el flujo
      // y da un «Connection closed while receiving data» que parece del
      // servidor y es de uno mismo.
      cuerpo = await utf8.decodeStream(respuesta);
    } on Object catch (e) {
      // Un fallo de DNS aquí **no** es «no hay red»: es exactamente el fallo que
      // esta prueba existe para cazar, así que se distingue de un corte de
      // conexión y se falla en vez de saltar.
      if (e is SocketException && e.osError?.errorCode == 11001) {
        fail('$salud no resuelve: el dominio de producción no existe. $e');
      }
      markTestSkipped('Sin red o el servidor no responde: $e');
      return;
    } finally {
      cliente.close(force: true);
    }

    expect(codigo, 200, reason: '$salud respondió $codigo');
    expect(cuerpo, contains('"status":"ok"'), reason: cuerpo);
  });

  test('y es https, o Android no la deja hablar', () {
    // Desde Android 9 el tráfico en claro está bloqueado. Un `http://` aquí no
    // daría un error legible: la aplicación simplemente no respondería nunca.
    expect(Entorno.apiProduccion, startsWith('https://'));
    expect(Entorno.apiProduccion, endsWith('/api/v1'));
  });
}

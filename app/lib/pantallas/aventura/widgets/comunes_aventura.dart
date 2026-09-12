/// Piezas compartidas por las cuatro pantallas de la Aventura (P22, P05, P06
/// y P07): el emblema del territorio, las apariciones en cascada, el pulso del
/// nodo activo y las tarjetas de aviso.
///
/// Aquí no se calcula nada del juego: todas las cifras llegan resueltas desde
/// el Reino y estos widgets solo las visten.
library;

import 'package:flutter/material.dart';

import '../../../datos/repositorios.dart';
import '../../../design/components.dart';
import '../../../design/tokens.dart';

// ---------------------------------------------------------------------------
// Utilidades de presentación
// ---------------------------------------------------------------------------

/// Convierte el color de acento que envía el Reino (`"#4DA3FF"`) en un [Color].
///
/// Devuelve `null` si el valor no es un hexadecimal reconocible, para que la
/// pantalla caiga en el color semántico del tema.
Color? colorDesdeHex(String? valor) {
  if (valor == null) return null;
  String texto = valor.trim().replaceAll('#', '').replaceAll('0x', '');
  if (texto.length == 3) {
    texto = texto.split('').map((String c) => '$c$c').join();
  }
  if (texto.length == 6) texto = 'FF$texto';
  if (texto.length != 8) return null;
  final int? entero = int.tryParse(texto, radix: 16);
  return entero == null ? null : Color(entero);
}

/// Emblemas por palabra clave: la pista del Reino (`icon_key`) o el nombre del
/// conocimiento deciden qué símbolo lleva el territorio.
const Map<String, IconData> _emblemasPorClave = <String, IconData>{
  'sql': Icons.storage_rounded,
  'data': Icons.insights_rounded,
  'dato': Icons.insights_rounded,
  'base': Icons.storage_rounded,
  'code': Icons.code_rounded,
  'program': Icons.code_rounded,
  'python': Icons.code_rounded,
  'cloud': Icons.cloud_rounded,
  'nube': Icons.cloud_rounded,
  'ai': Icons.auto_awesome_rounded,
  'ia': Icons.auto_awesome_rounded,
  'business': Icons.handshake_rounded,
  'negoc': Icons.handshake_rounded,
  'finan': Icons.account_balance_rounded,
  'lang': Icons.translate_rounded,
  'idioma': Icons.translate_rounded,
  'ingl': Icons.translate_rounded,
  'scien': Icons.science_rounded,
  'cienc': Icons.science_rounded,
  'math': Icons.calculate_rounded,
  'matem': Icons.calculate_rounded,
  'human': Icons.history_edu_rounded,
  'histor': Icons.history_edu_rounded,
  'art': Icons.palette_rounded,
  'music': Icons.music_note_rounded,
  'health': Icons.favorite_rounded,
  'salud': Icons.favorite_rounded,
  'law': Icons.gavel_rounded,
  'derech': Icons.gavel_rounded,
  'castle': Icons.castle_rounded,
  'forest': Icons.forest_rounded,
  'book': Icons.menu_book_rounded,
  'map': Icons.map_rounded,
};

/// Emblemas de reserva: dan variedad al Reino sin inventar significado.
const List<IconData> _emblemasDeReserva = <IconData>[
  Icons.castle_rounded,
  Icons.forest_rounded,
  Icons.terrain_rounded,
  Icons.temple_buddhist_rounded,
  Icons.water_rounded,
  Icons.local_library_rounded,
];

/// Elige el emblema del territorio a partir de la pista del Reino y del nombre.
IconData iconoDeTerritorio(String? iconoKey, [String? nombre]) {
  final String pista = '${iconoKey ?? ''} ${nombre ?? ''}'.toLowerCase();
  for (final MapEntry<String, IconData> entrada in _emblemasPorClave.entries) {
    if (pista.contains(entrada.key)) return entrada.value;
  }
  final String semilla = (nombre ?? iconoKey ?? '').trim();
  if (semilla.isEmpty) return Icons.auto_awesome_mosaic_rounded;
  return _emblemasDeReserva[semilla.hashCode.abs() % _emblemasDeReserva.length];
}

/// "40 min", "2 h", "1 h 30 min". Cadena vacía si no hay estimación.
String duracionLegible(int? minutos) {
  if (minutos == null || minutos <= 0) return '';
  if (minutos < 60) return '$minutos min';
  final int horas = minutos ~/ 60;
  final int resto = minutos % 60;
  return resto == 0 ? '$horas h' : '$horas h $resto min';
}

/// Misma idea que [duracionLegible], partiendo de segundos.
String duracionDesdeSegundos(int? segundos) {
  if (segundos == null || segundos <= 0) return '';
  if (segundos < 60) return 'menos de 1 min';
  return duracionLegible((segundos / 60).ceil());
}

/// Porcentaje ya resuelto por el servidor, redondeado para la interfaz.
String porcentajeLegible(double valor) => '${valor.round()} %';

/// Color semántico del estado de una Ruta.
Color colorDeEstadoRuta(BuildContext context, EstadoRuta estado) {
  final AteneaPalette p = context.paleta;
  return switch (estado) {
    EstadoRuta.borrador => p.textoSecundario,
    EstadoRuta.generando => p.info,
    EstadoRuta.porRevisar => p.advertencia,
    EstadoRuta.activa => p.arcano,
    EstadoRuta.completada => p.oro,
    EstadoRuta.archivada => p.textoSecundario,
    EstadoRuta.fallida => p.error,
  };
}

/// Icono que acompaña al estado de una Ruta (el color nunca va solo).
IconData iconoDeEstadoRuta(EstadoRuta estado) => switch (estado) {
      EstadoRuta.borrador => Icons.edit_note_rounded,
      EstadoRuta.generando => Icons.local_fire_department_rounded,
      EstadoRuta.porRevisar => Icons.fact_check_outlined,
      EstadoRuta.activa => Icons.explore_rounded,
      EstadoRuta.completada => Icons.emoji_events_rounded,
      EstadoRuta.archivada => Icons.inventory_2_outlined,
      EstadoRuta.fallida => Icons.report_gmailerrorred_rounded,
    };

// ---------------------------------------------------------------------------
// Emblema del territorio
// ---------------------------------------------------------------------------

/// Emblema de un territorio: el sello con el que se reconoce una Ruta.
///
/// En silueta representa un territorio todavía por descubrir: misma forma,
/// sin identidad, con etiqueta textual para que no dependa del color.
class EmblemaTerritorio extends StatelessWidget {
  const EmblemaTerritorio({
    super.key,
    this.nombre,
    this.iconoKey,
    this.colorAcento,
    this.tamano = 52,
    this.enSilueta = false,
    this.resplandor = false,
  });

  /// Nombre del conocimiento o de la Ruta, para elegir el emblema.
  final String? nombre;

  /// Pista de emblema que envía el Reino.
  final String? iconoKey;

  /// Color de acento del territorio, en hexadecimal.
  final String? colorAcento;

  /// Lado del emblema en dp.
  final double tamano;

  /// Territorio aún no descubierto.
  final bool enSilueta;

  /// Resplandor de territorio completado.
  final bool resplandor;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final Color color = enSilueta
        ? p.textoSecundario
        : (colorDesdeHex(colorAcento) ?? p.arcano);
    final IconData icono =
        enSilueta ? Icons.terrain_rounded : iconoDeTerritorio(iconoKey, nombre);

    return Semantics(
      label: enSilueta ? 'Territorio por descubrir' : null,
      child: Container(
        width: tamano,
        height: tamano,
        decoration: BoxDecoration(
          color: color.withValues(alpha: enSilueta ? 0.06 : 0.16),
          borderRadius: Redondeo.rTarjeta,
          border: Border.all(
            color: color.withValues(alpha: enSilueta ? 0.28 : 0.55),
            width: 1.4,
          ),
          boxShadow: resplandor ? Sombra.brillo(color, tamano / 4) : null,
        ),
        child: Icon(
          icono,
          size: tamano * 0.46,
          color: color.withValues(alpha: enSilueta ? 0.45 : 1),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Movimiento
// ---------------------------------------------------------------------------

/// Entrada en cascada de los elementos de una lista o de los nodos del mapa.
///
/// Con "reducir movimiento" activo el contenido aparece de golpe, ya colocado.
class AparecerEnCascada extends StatelessWidget {
  const AparecerEnCascada({required this.hijo, super.key, this.indice = 0});

  final Widget hijo;

  /// Posición en la lista: retrasa la entrada sin bloquear la interacción.
  final int indice;

  @override
  Widget build(BuildContext context) {
    if (reducirMovimiento(context)) return hijo;
    final Duration duracion = Movimiento.transicion +
        Duration(milliseconds: 55 * indice.clamp(0, 10));
    return TweenAnimationBuilder<double>(
      tween: Tween<double>(begin: 0, end: 1),
      duration: duracion,
      curve: Movimiento.estandar,
      builder: (BuildContext context, double t, Widget? nino) => Opacity(
        opacity: t.clamp(0, 1),
        child: Transform.translate(offset: Offset(0, (1 - t) * 14), child: nino),
      ),
      child: hijo,
    );
  }
}

/// Pulso suave alrededor del nodo donde está el usuario ("estás aquí").
///
/// Es la única animación en bucle del mapa y se detiene por completo cuando el
/// sistema pide reducir el movimiento.
class PulsoSuave extends StatefulWidget {
  const PulsoSuave({
    required this.hijo,
    required this.color,
    super.key,
    this.activo = true,
  });

  final Widget hijo;
  final Color color;
  final bool activo;

  @override
  State<PulsoSuave> createState() => _PulsoSuaveState();
}

class _PulsoSuaveState extends State<PulsoSuave>
    with SingleTickerProviderStateMixin {
  late final AnimationController _control = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1600),
  );

  bool get _debeLatir => widget.activo && !reducirMovimiento(context);

  void _sincronizar() {
    if (_debeLatir) {
      if (!_control.isAnimating) _control.repeat(reverse: true);
    } else if (_control.isAnimating) {
      _control
        ..stop()
        ..value = 0;
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _sincronizar();
  }

  @override
  void didUpdateWidget(covariant PulsoSuave anterior) {
    super.didUpdateWidget(anterior);
    _sincronizar();
  }

  @override
  void dispose() {
    _control.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!_debeLatir) return widget.hijo;
    return AnimatedBuilder(
      animation: _control,
      builder: (BuildContext context, Widget? nino) => DecoratedBox(
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          boxShadow: Sombra.brillo(widget.color, 6 + 10 * _control.value),
        ),
        child: nino,
      ),
      child: widget.hijo,
    );
  }
}

// ---------------------------------------------------------------------------
// Avisos
// ---------------------------------------------------------------------------

/// Tarjeta de aviso con voz del Reino: explica la situación y ofrece salida.
///
/// Se usa para el material insuficiente, el fallo de la forja, la espera larga
/// y el límite del plan. Nunca muestra códigos técnicos.
class TarjetaAviso extends StatelessWidget {
  const TarjetaAviso({
    required this.icono,
    required this.titulo,
    required this.mensaje,
    required this.color,
    super.key,
    this.textoAccion,
    this.alTocarAccion,
    this.textoSecundario,
    this.alTocarSecundario,
    this.pie,
  });

  final IconData icono;
  final String titulo;
  final String mensaje;
  final Color color;
  final String? textoAccion;
  final VoidCallback? alTocarAccion;
  final String? textoSecundario;
  final VoidCallback? alTocarSecundario;

  /// Contenido extra bajo el mensaje (una lista de temas, por ejemplo).
  final Widget? pie;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    return TarjetaAtenea(
      colorBorde: color.withValues(alpha: 0.5),
      semantica: '$titulo. $mensaje',
      hijo: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Icon(icono, color: color, size: 22),
              const SizedBox(width: Espacio.sm),
              Expanded(
                child: Text(titulo, style: context.textos.titleMedium),
              ),
            ],
          ),
          const SizedBox(height: Espacio.xs),
          Text(
            mensaje,
            style: context.textos.bodyMedium?.copyWith(color: p.textoSecundario),
          ),
          if (pie != null) ...<Widget>[
            const SizedBox(height: Espacio.sm),
            pie!,
          ],
          if (textoAccion != null || textoSecundario != null) ...<Widget>[
            const SizedBox(height: Espacio.sm),
            Wrap(
              spacing: Espacio.xs,
              runSpacing: Espacio.xs,
              children: <Widget>[
                if (textoAccion != null)
                  FilledButton(
                    onPressed: alTocarAccion,
                    child: Text(textoAccion!),
                  ),
                if (textoSecundario != null)
                  OutlinedButton(
                    onPressed: alTocarSecundario,
                    child: Text(textoSecundario!),
                  ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

/// Franja discreta de estado (sin conexión, reintentando, espera larga).
class FranjaEstado extends StatelessWidget {
  const FranjaEstado({
    required this.icono,
    required this.mensaje,
    required this.color,
    super.key,
    this.textoAccion,
    this.alTocarAccion,
  });

  final IconData icono;
  final String mensaje;
  final Color color;
  final String? textoAccion;
  final VoidCallback? alTocarAccion;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: Espacio.sm,
        vertical: Espacio.xs,
      ),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: Redondeo.rBoton,
        border: Border.all(color: color.withValues(alpha: 0.35)),
      ),
      child: Row(
        children: <Widget>[
          Icon(icono, size: 18, color: color),
          const SizedBox(width: Espacio.xs),
          Expanded(
            child: Text(mensaje, style: context.textos.bodyMedium),
          ),
          if (textoAccion != null)
            TextButton(onPressed: alTocarAccion, child: Text(textoAccion!)),
        ],
      ),
    );
  }
}

/// Fila de estrellas del Desafío del módulo (0 a 3), con etiqueta accesible.
class Estrellas extends StatelessWidget {
  const Estrellas({required this.cantidad, super.key, this.tamano = 16});

  final int cantidad;
  final double tamano;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    return Semantics(
      label: '$cantidad de 3 estrellas',
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          for (int i = 0; i < 3; i++)
            Icon(
              i < cantidad ? Icons.star_rounded : Icons.star_outline_rounded,
              size: tamano,
              color: i < cantidad ? p.oro : p.textoSecundario,
            ),
        ],
      ),
    );
  }
}

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'theme.dart';
import 'tokens.dart';

/// Biblioteca de componentes de Atenea.
///
/// Todas las pantallas se construyen con estas piezas para que la interfaz se
/// mantenga coherente: mismos radios, mismos espaciados, mismos colores
/// semánticos y las mismas reglas de accesibilidad (área táctil mínima de
/// 48 dp, el color nunca como único portador de significado, y respeto por la
/// preferencia de "reducir movimiento" del sistema).

/// Los seis medallones de juego del documento de UX.
enum Medallon {
  xp('Experiencia', Icons.auto_awesome_rounded),
  oro('Oro', Icons.monetization_on_rounded),
  racha('Racha', Icons.local_fire_department_rounded),
  dominio('Dominio', Icons.psychology_rounded),
  tiempo('Tiempo', Icons.hourglass_bottom_rounded),
  nivel('Nivel', Icons.shield_rounded);

  const Medallon(this.etiqueta, this.icono);

  final String etiqueta;
  final IconData icono;

  Color color(BuildContext context) => switch (this) {
        Medallon.xp => context.paleta.oro,
        Medallon.oro => context.paleta.oro,
        Medallon.racha => context.paleta.brasa,
        Medallon.dominio => context.paleta.dominio,
        Medallon.tiempo => context.paleta.textoSecundario,
        Medallon.nivel => context.paleta.arcano,
      };
}

/// ¿El sistema pide reducir el movimiento?
bool reducirMovimiento(BuildContext context) =>
    MediaQuery.maybeDisableAnimationsOf(context) ?? false;

/// ¿El aprendiz quiere que el móvil vibre?
///
/// El hermano de `reducirMovimiento`, y por la misma razón: esta biblioteca no
/// conoce la sesión ni debe conocerla, así que el valor baja por el árbol y
/// aquí sólo se lee. Lo inyecta `AplicacionAtenea` desde los ajustes.
///
/// El movimiento tuvo suerte: el sistema operativo ya tenía una preferencia
/// estándar (`MediaQuery.disableAnimations`) donde apoyarse. El tacto no la
/// tiene, así que la lleva este portador.
///
/// Por defecto, sí. Antes de iniciar sesión no hay ajustes que consultar, y en
/// ese tramo —el acceso, la creación del héroe— el toque ya existía; callarlo
/// por falta de datos sería un cambio que nadie pidió.
bool hapticaActiva(BuildContext context) =>
    PreferenciasDeTacto.maybeOf(context) ?? true;

/// Portador de la preferencia de tacto. Ver `hapticaActiva`.
class PreferenciasDeTacto extends InheritedWidget {
  const PreferenciasDeTacto({
    required this.activa,
    required super.child,
    super.key,
  });

  /// Lo que el aprendiz eligió en Ajustes.
  final bool activa;

  static bool? maybeOf(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<PreferenciasDeTacto>()?.activa;

  @override
  bool updateShouldNotify(PreferenciasDeTacto anterior) =>
      anterior.activa != activa;
}

/// El toque háptico de Atenea: el de Flutter, pero obedeciendo a Ajustes.
///
/// Sustituye a `HapticFeedback` en toda la aplicación, y la diferencia que
/// importa es el `context` obligatorio: sin él no hay forma de saber si el
/// aprendiz quiere que el móvil vibre. Llamar a `HapticFeedback` directamente
/// compilaba igual de bien y vibraba con el interruptor apagado; ese olvido,
/// repetido en diez sitios, es justo lo que esto viene a cerrar.
abstract final class Tacto {
  /// Al elegir algo de una lista, una rejilla o un carrusel.
  static void seleccion(BuildContext context) =>
      _tocar(context, HapticFeedback.selectionClick);

  /// Al rechazar una acción: un formulario incompleto, un botón que no procede.
  static void ligero(BuildContext context) =>
      _tocar(context, HapticFeedback.lightImpact);

  /// Al celebrar: subida de nivel, ítem desbloqueado, héroe creado.
  static void medio(BuildContext context) =>
      _tocar(context, HapticFeedback.mediumImpact);

  static void _tocar(BuildContext context, Future<void> Function() toque) {
    if (!hapticaActiva(context)) return;
    unawaited(toque());
  }
}

/// Andamio estándar: fondo del tema, ancho de lectura contenido y padding
/// consistente.
class PantallaAtenea extends StatelessWidget {
  const PantallaAtenea({
    required this.cuerpo,
    super.key,
    this.titulo,
    this.acciones,
    this.encabezado,
    this.piePersistente,
    this.mostrarVolver = false,
    this.cerrarEnLugarDeVolver = false,
    this.alCerrar,
    this.padding = const EdgeInsets.fromLTRB(Espacio.md, Espacio.xs, Espacio.md, Espacio.xl),
    this.limitarAnchoLectura = true,
  });

  final Widget cuerpo;
  final String? titulo;
  final List<Widget>? acciones;

  /// Contenido fijo bajo la barra superior (por ejemplo, una barra de progreso).
  final Widget? encabezado;

  /// Barra inferior fija (por ejemplo, el botón "Comprobar" de una pregunta).
  final Widget? piePersistente;

  final bool mostrarVolver;

  /// En los flujos inmersivos (lección, evaluación, generación) el control de
  /// salida es una X, no una flecha.
  final bool cerrarEnLugarDeVolver;
  final VoidCallback? alCerrar;

  final EdgeInsets padding;
  final bool limitarAnchoLectura;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final bool hayBarra = titulo != null || mostrarVolver || cerrarEnLugarDeVolver || acciones != null;

    Widget contenido = Padding(padding: padding, child: cuerpo);
    if (limitarAnchoLectura) {
      contenido = Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: Medida.lecturaMax),
          child: contenido,
        ),
      );
    }

    return Scaffold(
      backgroundColor: p.fondo,
      appBar: hayBarra
          ? AppBar(
              title: titulo == null ? null : Text(titulo!),
              actions: acciones,
              leading: cerrarEnLugarDeVolver
                  ? IconButton(
                      icon: const Icon(Icons.close_rounded),
                      tooltip: 'Cerrar',
                      onPressed: alCerrar ?? () => Navigator.of(context).maybePop(),
                    )
                  : (mostrarVolver
                      ? IconButton(
                          icon: const Icon(Icons.arrow_back_rounded),
                          tooltip: 'Volver',
                          onPressed: () => Navigator.of(context).maybePop(),
                        )
                      : null),
              bottom: encabezado == null
                  ? null
                  : PreferredSize(
                      preferredSize: const Size.fromHeight(48),
                      child: Padding(
                        padding: const EdgeInsets.fromLTRB(Espacio.md, 0, Espacio.md, Espacio.xs),
                        child: encabezado,
                      ),
                    ),
            )
          : null,
      body: SafeArea(child: contenido),
      bottomNavigationBar: piePersistente == null
          ? null
          : SafeArea(
              minimum: const EdgeInsets.fromLTRB(Espacio.md, 0, Espacio.md, Espacio.md),
              child: piePersistente!,
            ),
    );
  }
}

/// Tarjeta base: superficie, borde sutil, radio de 16 dp y, opcionalmente,
/// resplandor de rareza.
class TarjetaAtenea extends StatelessWidget {
  const TarjetaAtenea({
    required this.hijo,
    super.key,
    this.alTocar,
    this.padding = const EdgeInsets.all(Espacio.md),
    this.elevada = false,
    this.colorBorde,
    this.brillo,
    this.semantica,
  });

  final Widget hijo;
  final VoidCallback? alTocar;
  final EdgeInsets padding;
  final bool elevada;
  final Color? colorBorde;

  /// Radio del resplandor de color (rareza). Cero o nulo: sin brillo.
  final double? brillo;
  final String? semantica;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final Color borde = colorBorde ?? p.borde;

    final Widget tarjeta = AnimatedContainer(
      duration: Movimiento.micro,
      curve: Movimiento.estandar,
      decoration: BoxDecoration(
        color: elevada ? p.superficieElevada : p.superficie,
        borderRadius: Redondeo.rTarjeta,
        border: Border.all(color: borde, width: colorBorde != null ? 1.5 : 1),
        boxShadow: (brillo ?? 0) > 0 ? Sombra.brillo(borde, brillo!) : null,
      ),
      padding: padding,
      child: hijo,
    );

    final Widget conToque = alTocar == null
        ? tarjeta
        : Material(
            color: Colors.transparent,
            child: InkWell(
              onTap: () {
                Tacto.seleccion(context);
                alTocar!();
              },
              borderRadius: Redondeo.rTarjeta,
              child: tarjeta,
            ),
          );

    return semantica == null ? conToque : Semantics(label: semantica, child: conToque);
  }
}

/// Encabezado de sección con título y acción opcional a la derecha.
class EncabezadoSeccion extends StatelessWidget {
  const EncabezadoSeccion({
    required this.titulo,
    super.key,
    this.subtitulo,
    this.textoAccion,
    this.alTocarAccion,
  });

  final String titulo;
  final String? subtitulo;
  final String? textoAccion;
  final VoidCallback? alTocarAccion;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: Espacio.xs, top: Espacio.lg),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(titulo, style: context.textos.headlineSmall),
                if (subtitulo != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Text(
                      subtitulo!,
                      style: context.textos.bodyMedium?.copyWith(color: context.paleta.textoSecundario),
                    ),
                  ),
              ],
            ),
          ),
          if (textoAccion != null)
            TextButton(onPressed: alTocarAccion, child: Text(textoAccion!)),
        ],
      ),
    );
  }
}

/// Medallón compacto de estadística: icono, cifra y etiqueta.
///
/// Es la unidad con la que se muestran XP, oro, racha, dominio, tiempo y nivel
/// en el panel principal y en el perfil.
class FichaMedallon extends StatelessWidget {
  const FichaMedallon({
    required this.tipo,
    required this.valor,
    super.key,
    this.etiqueta,
    this.compacto = false,
    this.alTocar,
  });

  final Medallon tipo;
  final String valor;
  final String? etiqueta;
  final bool compacto;
  final VoidCallback? alTocar;

  @override
  Widget build(BuildContext context) {
    final Color color = tipo.color(context);
    final String texto = etiqueta ?? tipo.etiqueta;

    if (compacto) {
      return Semantics(
        label: '$texto: $valor',
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(tipo.icono, size: 18, color: color),
            const SizedBox(width: Espacio.xxs + 2),
            Text(valor, style: Cifras.pequena(context).copyWith(color: context.paleta.textoPrimario)),
          ],
        ),
      );
    }

    return TarjetaAtenea(
      alTocar: alTocar,
      padding: const EdgeInsets.symmetric(horizontal: Espacio.sm, vertical: Espacio.sm),
      semantica: '$texto: $valor',
      hijo: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(tipo.icono, size: 20, color: color),
          const SizedBox(height: Espacio.xs),
          Text(valor, style: Cifras.media(context)),
          Text(
            texto,
            style: context.textos.bodySmall?.copyWith(color: context.paleta.textoSecundario),
          ),
        ],
      ),
    );
  }
}

/// Barra de progreso con etiqueta y cifra opcional.
class BarraProgreso extends StatelessWidget {
  const BarraProgreso({
    required this.valor,
    super.key,
    this.etiqueta,
    this.textoDerecha,
    this.color,
    this.alto = 10,
    this.animar = true,
  });

  /// Progreso entre 0 y 1.
  final double valor;
  final String? etiqueta;
  final String? textoDerecha;
  final Color? color;
  final double alto;
  final bool animar;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final Color c = color ?? p.arcano;
    final double v = valor.clamp(0.0, 1.0);
    final bool animado = animar && !reducirMovimiento(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        if (etiqueta != null || textoDerecha != null)
          Padding(
            padding: const EdgeInsets.only(bottom: Espacio.xxs + 2),
            child: Row(
              children: <Widget>[
                if (etiqueta != null)
                  Expanded(
                    child: Text(
                      etiqueta!,
                      style: context.textos.bodyMedium?.copyWith(color: p.textoSecundario),
                    ),
                  ),
                if (textoDerecha != null)
                  Text(textoDerecha!, style: Cifras.pequena(context)),
              ],
            ),
          ),
        Semantics(
          label: etiqueta,
          value: '${(v * 100).round()} por ciento',
          child: ClipRRect(
            borderRadius: Redondeo.rPildora,
            child: SizedBox(
              height: alto,
              child: animado
                  ? TweenAnimationBuilder<double>(
                      tween: Tween<double>(begin: 0, end: v),
                      duration: Movimiento.transicion,
                      curve: Movimiento.estandar,
                      builder: (BuildContext context, double t, _) => LinearProgressIndicator(
                        value: t,
                        backgroundColor: p.borde,
                        valueColor: AlwaysStoppedAnimation<Color>(c),
                      ),
                    )
                  : LinearProgressIndicator(
                      value: v,
                      backgroundColor: p.borde,
                      valueColor: AlwaysStoppedAnimation<Color>(c),
                    ),
            ),
          ),
        ),
      ],
    );
  }
}

/// Etiqueta de rareza: color más texto, nunca color solo.
class ChipRareza extends StatelessWidget {
  const ChipRareza({required this.rareza, super.key});

  final Rareza rareza;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: Espacio.xs, vertical: 3),
      decoration: BoxDecoration(
        color: rareza.color.withValues(alpha: 0.14),
        borderRadius: Redondeo.rPildora,
        border: Border.all(color: rareza.color.withValues(alpha: 0.7)),
      ),
      child: Text(
        rareza.etiqueta,
        style: context.textos.bodySmall?.copyWith(
          color: rareza.color,
          fontWeight: FontWeight.w800,
        ),
      ),
    );
  }
}

/// Píldora informativa neutra (territorio, tipo de misión, estado).
class Pildora extends StatelessWidget {
  const Pildora({
    required this.texto,
    super.key,
    this.icono,
    this.color,
  });

  final String texto;
  final IconData? icono;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final Color c = color ?? context.paleta.textoSecundario;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: Espacio.xs + 2, vertical: 4),
      decoration: BoxDecoration(
        color: c.withValues(alpha: 0.12),
        borderRadius: Redondeo.rPildora,
        border: Border.all(color: c.withValues(alpha: 0.35)),
      ),
      // Un solo `Text` con el icono incrustado, en vez de un `Row`: dentro de
      // una fila, los hijos sin `Expanded` reciben anchura infinita y el texto
      // nunca se parte, así que una etiqueta larga en un ancho estrecho —o con
      // la fuente del sistema al 200 %— desbordaba. Así el texto hereda la
      // anchura real del contenedor y se reparte en dos líneas cuando hace
      // falta. Sigue encogiendo hasta su tamaño natural donde sobra sitio.
      child: Text.rich(
        TextSpan(
          children: <InlineSpan>[
            if (icono != null)
              WidgetSpan(
                alignment: PlaceholderAlignment.middle,
                child: Padding(
                  padding: const EdgeInsets.only(right: 4),
                  child: Icon(icono, size: 14, color: c),
                ),
              ),
            TextSpan(text: texto),
          ],
        ),
        style: context.textos.bodySmall?.copyWith(color: c, fontWeight: FontWeight.w700),
      ),
    );
  }
}

/// Botón principal de ancho completo.
class BotonPrimario extends StatelessWidget {
  const BotonPrimario({
    required this.texto,
    required this.alTocar,
    super.key,
    this.subtitulo,
    this.icono,
    this.cargando = false,
  });

  final String texto;
  final String? subtitulo;
  final IconData? icono;
  final VoidCallback? alTocar;
  final bool cargando;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    return FilledButton(
      onPressed: cargando ? null : alTocar,
      child: cargando
          ? const SizedBox(
              height: 20,
              width: 20,
              child: CircularProgressIndicator(strokeWidth: 2.4, color: Colors.white),
            )
          : Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: <Widget>[
                if (icono != null) ...<Widget>[
                  Icon(icono, size: 20),
                  const SizedBox(width: Espacio.xs),
                ],
                Flexible(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: <Widget>[
                      Text(texto, textAlign: TextAlign.center),
                      if (subtitulo != null)
                        Text(
                          subtitulo!,
                          textAlign: TextAlign.center,
                          style: context.textos.bodySmall?.copyWith(
                            color: p.sobreArcano.withValues(alpha: 0.82),
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                    ],
                  ),
                ),
              ],
            ),
    );
  }
}

/// Estado vacío con icono, mensaje y acción opcional.
class EstadoVacio extends StatelessWidget {
  const EstadoVacio({
    required this.titulo,
    required this.mensaje,
    super.key,
    this.icono = Icons.auto_stories_rounded,
    this.textoAccion,
    this.alTocarAccion,
  });

  final String titulo;
  final String mensaje;
  final IconData icono;
  final String? textoAccion;
  final VoidCallback? alTocarAccion;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(Espacio.lg),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(icono, size: 44, color: p.textoSecundario),
            const SizedBox(height: Espacio.md),
            Text(titulo, style: context.textos.headlineSmall, textAlign: TextAlign.center),
            const SizedBox(height: Espacio.xs),
            Text(
              mensaje,
              style: context.textos.bodyLarge?.copyWith(color: p.textoSecundario),
              textAlign: TextAlign.center,
            ),
            if (textoAccion != null) ...<Widget>[
              const SizedBox(height: Espacio.lg),
              FilledButton(onPressed: alTocarAccion, child: Text(textoAccion!)),
            ],
          ],
        ),
      ),
    );
  }
}

/// Estado de error con posibilidad de reintentar.
class EstadoError extends StatelessWidget {
  const EstadoError({
    required this.mensaje,
    super.key,
    this.titulo = 'Algo no salió bien',
    this.alReintentar,
  });

  final String titulo;
  final String mensaje;
  final VoidCallback? alReintentar;

  @override
  Widget build(BuildContext context) {
    return EstadoVacio(
      icono: Icons.error_outline_rounded,
      titulo: titulo,
      mensaje: mensaje,
      textoAccion: alReintentar == null ? null : 'Reintentar',
      alTocarAccion: alReintentar,
    );
  }
}

/// Bloque de carga con esqueleto sobrio (sin destellos agresivos).
class EstadoCarga extends StatelessWidget {
  const EstadoCarga({super.key, this.mensaje});

  final String? mensaje;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          const CircularProgressIndicator(),
          if (mensaje != null) ...<Widget>[
            const SizedBox(height: Espacio.md),
            Text(
              mensaje!,
              style: context.textos.bodyMedium?.copyWith(color: context.paleta.textoSecundario),
              textAlign: TextAlign.center,
            ),
          ],
        ],
      ),
    );
  }
}

/// Rectángulo de esqueleto para listas mientras cargan.
class Esqueleto extends StatelessWidget {
  const Esqueleto({super.key, this.alto = 16, this.ancho, this.radio = Redondeo.chip});

  final double alto;
  final double? ancho;
  final double radio;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: alto,
      width: ancho,
      decoration: BoxDecoration(
        color: context.paleta.borde.withValues(alpha: 0.6),
        borderRadius: BorderRadius.circular(radio),
      ),
    );
  }
}

/// Fila de par etiqueta/valor, usada en fichas y hojas de detalle.
class FilaDato extends StatelessWidget {
  const FilaDato({required this.etiqueta, required this.valor, super.key, this.icono});

  final String etiqueta;
  final String valor;
  final IconData? icono;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: Espacio.xxs + 2),
      child: Row(
        children: <Widget>[
          if (icono != null) ...<Widget>[
            Icon(icono, size: 16, color: p.textoSecundario),
            const SizedBox(width: Espacio.xs),
          ],
          Expanded(
            child: Text(
              etiqueta,
              style: context.textos.bodyMedium?.copyWith(color: p.textoSecundario),
            ),
          ),
          Text(valor, style: Cifras.pequena(context).copyWith(color: p.textoPrimario)),
        ],
      ),
    );
  }
}

/// Ornamento de esquina: filigrana discreta reservada a las pantallas de
/// celebración y a las tarjetas de ítem, nunca a la interfaz general.
class OrnamentoEsquina extends StatelessWidget {
  const OrnamentoEsquina({required this.color, super.key, this.tamano = 28});

  final Color color;
  final double tamano;

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: CustomPaint(
        size: Size.square(tamano),
        painter: _PintorOrnamento(color),
      ),
    );
  }
}

class _PintorOrnamento extends CustomPainter {
  const _PintorOrnamento(this.color);

  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final Paint trazo = Paint()
      ..color = color.withValues(alpha: 0.85)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.4
      ..strokeCap = StrokeCap.round;

    final double s = size.width;
    canvas
      ..drawLine(Offset(0, s * 0.42), Offset(0, s * 0.12), trazo)
      ..drawArc(Rect.fromLTWH(0, 0, s * 0.24, s * 0.24), 3.14159, 1.5708, false, trazo)
      ..drawLine(Offset(s * 0.12, 0), Offset(s * 0.42, 0), trazo)
      ..drawCircle(Offset(s * 0.52, s * 0.12), 1.8, trazo)
      ..drawCircle(Offset(s * 0.12, s * 0.52), 1.8, trazo);
  }

  @override
  bool shouldRepaint(covariant _PintorOrnamento old) => old.color != color;
}

/// Cifra que se anima al cambiar (XP, oro, dominio).
///
/// Respeta "reducir movimiento": en ese caso salta al valor final.
class CifraAnimada extends StatelessWidget {
  const CifraAnimada({
    required this.valor,
    super.key,
    this.estilo,
    this.sufijo = '',
    this.prefijo = '',
    this.duracion = Movimiento.transicion,
  });

  final num valor;
  final TextStyle? estilo;
  final String prefijo;
  final String sufijo;
  final Duration duracion;

  @override
  Widget build(BuildContext context) {
    final TextStyle e = estilo ?? Cifras.grande(context);
    if (reducirMovimiento(context)) {
      return Text('$prefijo${valor.round()}$sufijo', style: e);
    }
    return TweenAnimationBuilder<double>(
      tween: Tween<double>(begin: 0, end: valor.toDouble()),
      duration: duracion,
      curve: Movimiento.estandar,
      builder: (BuildContext context, double v, _) =>
          Text('$prefijo${v.round()}$sufijo', style: e),
    );
  }
}

/// P04 · Inicio: el panel del héroe.
///
/// La pantalla más importante del producto. Responde "¿qué hago ahora?" en un
/// segundo con un orden vertical fijo, tomado del documento de experiencia:
///
/// 1. Saludo, avatar, nivel y título de rango, barra de XP, racha y oro.
/// 2. Banner de la ruta que se está forjando, si la hay.
/// 3. Misión de hoy: el objetivo diario con su progreso.
/// 4. "Continúa tu aventura": una sola actividad concreta y su recompensa.
/// 5. Tus conocimientos, con su dominio (máximo tres y "Ver todo").
/// 6. Esta semana: tiempo, lecciones y logros.
///
/// Todo sale de **una sola llamada** a `/dashboard`; la app no calcula XP,
/// oro, nivel ni dominio.
library;

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../data/errores.dart';
import '../../datos/repositorios.dart';
import '../../design/components.dart';
import '../../design/tokens.dart';
import '../../estado/gamificacion.dart';
import '../../estado/leccion.dart';
import '../../estado/panel.dart';
import '../../estado/sesion.dart';
import '../../navegacion/rutas.dart';
import '../repaso/widgets/tarjeta_repaso.dart';
import 'widgets/banner_generacion.dart';
import 'widgets/cabecera_heroe.dart';
import 'widgets/esqueletos.dart';
import 'widgets/fila_conocimiento.dart';
import 'widgets/formatos.dart';
import 'widgets/notificaciones.dart';
import 'widgets/tarjeta_continuar.dart';
import 'widgets/tarjeta_objetivo_dia.dart';

/// Panel principal del héroe.
class PantallaInicio extends StatefulWidget {
  const PantallaInicio({super.key});

  @override
  State<PantallaInicio> createState() => _PantallaInicioState();
}

class _PantallaInicioState extends State<PantallaInicio>
    with WidgetsBindingObserver {
  /// Cuántos conocimientos se ven sin abrir "Ver todo".
  static const int _conocimientosVisibles = 3;

  /// Cuántos repasos recomendados se ven sin abrir "Ver todos".
  static const int _repasosVisibles = 2;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((Duration _) {
      if (!mounted) return;
      context.read<ControladorPanel>().cargar();
      context.read<ControladorLeccion>().cargarRepasosRecomendados();
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState estado) {
    // Al volver de segundo plano el día puede haber cambiado: racha, objetivo
    // y misiones se piden de nuevo si ya envejecieron.
    if (estado == AppLifecycleState.resumed && mounted) {
      context.read<ControladorPanel>().cargar();
    }
  }

  // ---------------------------------------------------------------------
  // Navegación
  // ---------------------------------------------------------------------

  void _continuar(AccionContinuar accion) {
    final String? leccionId = accion.leccionId;
    final String? moduloId = accion.moduloId;
    final String? temaId = accion.temaId;
    final String? rutaId = accion.rutaId;

    final String? destino = switch (accion.tipo) {
      TipoAccionContinuar.leccion =>
        leccionId == null ? null : Rutas.leccion(leccionId),
      TipoAccionContinuar.evaluacion =>
        moduloId == null ? null : Rutas.evaluacion(moduloId),
      TipoAccionContinuar.repaso ||
      TipoAccionContinuar.practica =>
        temaId == null ? null : Rutas.repaso(temaId),
      TipoAccionContinuar.crearRuta => Rutas.crearRuta,
      TipoAccionContinuar.verGeneracion =>
        rutaId == null ? null : Rutas.generacion(rutaId),
      TipoAccionContinuar.ninguna => null,
    };

    if (destino != null) {
      context.push(destino);
      return;
    }
    if (rutaId != null) {
      context.push(Rutas.ruta(rutaId));
      return;
    }
    context.go(Rutas.aventura);
  }

  void _abrirGeneracion(BannerGeneracion banner) {
    final String? rutaId = banner.rutaId;
    if (rutaId == null) {
      context.go(Rutas.aventura);
      return;
    }
    context.push(Rutas.generacion(rutaId));
  }

  void _abrirRutaDelBanner(BannerGeneracion banner) {
    final String? rutaId = banner.rutaId;
    if (rutaId == null) {
      context.go(Rutas.aventura);
      return;
    }
    context.push(Rutas.ruta(rutaId));
  }

  // ---------------------------------------------------------------------
  // Construcción
  // ---------------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    final ControladorPanel controlador = context.watch<ControladorPanel>();
    final ControladorSesion sesion = context.watch<ControladorSesion>();
    final ControladorGamificacion gami = context.watch<ControladorGamificacion>();
    final Panel? panel = controlador.panel;

    final int sinLeer = gami.notificaciones.isEmpty
        ? (panel?.notificacionesSinLeer ?? 0)
        : gami.sinLeer;

    return PantallaAtenea(
      padding: EdgeInsets.zero,
      cuerpo: RefreshIndicator(
        onRefresh: controlador.refrescar,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(
            Espacio.md,
            Espacio.xs,
            Espacio.md,
            Espacio.xxl,
          ),
          children: <Widget>[
            _Saludo(
              texto: saludoDelReino(
                panel?.claveSaludo ?? '',
                panel?.personaje?.nombre ?? sesion.nombreVisible,
              ),
              sinLeer: sinLeer,
              alTocarCampana: () => abrirBandejaNotificaciones(context),
            ),
            const SizedBox(height: Espacio.sm),
            if (controlador.avisoEnCache)
              _AvisoEnCache(
                mensaje: controlador.error?.mensaje ??
                    'No pudimos actualizar tu Reino.',
                alReintentar: controlador.refrescar,
              ),
            if (controlador.errorSinDatos)
              _ErrorDelPanel(error: controlador.error, alReintentar: controlador.refrescar)
            else if (panel == null)
              const EsqueletoInicio()
            else
              ..._bloques(context, controlador, panel, gami),
          ],
        ),
      ),
    );
  }

  List<Widget> _bloques(
    BuildContext context,
    ControladorPanel controlador,
    Panel panel,
    ControladorGamificacion gami,
  ) {
    final AteneaPalette p = context.paleta;
    final BannerGeneracion? banner = panel.bannerGeneracion;
    final List<AreaConocimiento> conocimientos = panel.conocimientos;
    final List<AreaConocimiento> visibles =
        conocimientos.take(_conocimientosVisibles).toList(growable: false);
    final List<SugerenciaRepaso> repasos =
        context.watch<ControladorLeccion>().repasosRecomendados;

    return <Widget>[
      CabeceraHeroe(
        personaje: panel.personaje,
        racha: panel.racha,
        saldoOro: panel.saldoOro,
        capas: panel.capasAvatar,
        alTocarAvatar: () => context.go(Rutas.personaje),
        alTocarRacha: () => context.go(Rutas.racha),
        alTocarOro: () => context.go(Rutas.mercado),
      ),
      if (banner != null) ...<Widget>[
        const SizedBox(height: Espacio.md),
        BannerDeGeneracion(
          banner: banner,
          alVerGeneracion: () => _abrirGeneracion(banner),
          alAbrirRuta: () => _abrirRutaDelBanner(banner),
        ),
      ],
      const SizedBox(height: Espacio.md),
      TarjetaObjetivoDia(
        objetivo: panel.objetivoDiario,
        misiones: panel.misiones,
        alVerMisiones: () => context.go(Rutas.misiones),
      ),
      const SizedBox(height: Espacio.md),
      TarjetaContinuar(
        accion: panel.accionContinuar,
        sinRutas: panel.sinRutas,
        alContinuar: () => _continuar(panel.accionContinuar),
        alCrearRuta: () => context.push(Rutas.crearRuta),
        alExplorar: () => context.go(Rutas.aventura),
      ),

      // --- Tus conocimientos ---------------------------------------------
      EncabezadoSeccion(
        titulo: 'Tus conocimientos',
        textoAccion: conocimientos.length > _conocimientosVisibles ? 'Ver todo' : null,
        alTocarAccion: () => context.go(Rutas.aventura),
      ),
      if (visibles.isEmpty)
        TarjetaAtenea(
          hijo: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Text(
                'Todavía no hay territorios en tu mapa',
                style: context.textos.titleMedium,
              ),
              const SizedBox(height: Espacio.xxs),
              Text(
                'En cuanto completes tu primera lección, aquí verás tu dominio '
                'crecer en cada conocimiento.',
                style: context.textos.bodyMedium?.copyWith(
                  color: p.textoSecundario,
                ),
              ),
            ],
          ),
        )
      else
        for (final AreaConocimiento area in visibles) ...<Widget>[
          FilaConocimiento(
            area: area,
            // «Pide repaso» prometía justo eso y llevaba al mapa del
            // Territorio, que no repasa nada: ahí no hay ni una pregunta que
            // responder. Ahora sí lleva a los repasos recomendados.
            alTocar: () => context.go(
              area.estado.pideRepaso ? Rutas.repasosRecomendados : Rutas.aventura,
            ),
          ),
          const SizedBox(height: Espacio.xs),
        ],
      Align(
        alignment: Alignment.centerLeft,
        child: TextButton.icon(
          onPressed: () => context.push(Rutas.crearRuta),
          icon: const Icon(Icons.add_rounded),
          label: const Text('Crear nueva ruta'),
        ),
      ),

      // --- Repasos pendientes ----------------------------------------------
      // El servidor calcula de verdad qué temas se están olvidando; esta es
      // la primera vista de esa lista mientras el aprendiz estudia con
      // normalidad, no solo al reprobar un desafío o terminar una Ruta.
      if (repasos.isNotEmpty) ...<Widget>[
        EncabezadoSeccion(
          titulo: 'Repasos pendientes',
          textoAccion: repasos.length > _repasosVisibles ? 'Ver todos' : null,
          alTocarAccion: () => context.go(Rutas.repasosRecomendados),
        ),
        for (final SugerenciaRepaso s in repasos.take(_repasosVisibles))
          TarjetaRepaso(
            sugerencia: s,
            alTocar: () => context.push(Rutas.repaso(s.temaId)),
          ),
      ],

      // --- Esta semana -----------------------------------------------------
      const EncabezadoSeccion(titulo: 'Esta semana'),
      _ResumenSemana(
        semana: panel.estadisticasSemana,
        alVerPerfil: () => context.go(Rutas.perfil),
        alVerLogros: () => context.go(Rutas.logros),
      ),
      const SizedBox(height: Espacio.lg),
      _CierreDelDia(racha: panel.racha, objetivo: panel.objetivoDiario),
      if (controlador.refrescando) ...<Widget>[
        const SizedBox(height: Espacio.md),
        Center(
          child: Text(
            'Actualizando tu Reino…',
            style: context.textos.bodySmall?.copyWith(color: p.textoSecundario),
          ),
        ),
      ],
    ];
  }
}

/// Saludo y campana de mensajes.
class _Saludo extends StatelessWidget {
  const _Saludo({
    required this.texto,
    required this.sinLeer,
    required this.alTocarCampana,
  });

  final String texto;
  final int sinLeer;
  final VoidCallback alTocarCampana;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: <Widget>[
        Expanded(
          child: Text(
            texto,
            style: context.textos.headlineMedium,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
        ),
        const SizedBox(width: Espacio.xs),
        CampanaNotificaciones(sinLeer: sinLeer, alTocar: alTocarCampana),
      ],
    );
  }
}

/// Aviso discreto: se muestran datos guardados porque la red falló.
class _AvisoEnCache extends StatelessWidget {
  const _AvisoEnCache({required this.mensaje, required this.alReintentar});

  final String mensaje;
  final VoidCallback alReintentar;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    return Padding(
      padding: const EdgeInsets.only(bottom: Espacio.sm),
      child: Container(
        padding: const EdgeInsets.fromLTRB(
          Espacio.sm,
          Espacio.xs,
          Espacio.xs,
          Espacio.xs,
        ),
        decoration: BoxDecoration(
          color: p.advertencia.withValues(alpha: 0.12),
          borderRadius: Redondeo.rBoton,
          border: Border.all(color: p.advertencia.withValues(alpha: 0.4)),
        ),
        child: Row(
          children: <Widget>[
            Icon(Icons.cloud_off_rounded, size: Tipo.cuerpo, color: p.advertencia),
            const SizedBox(width: Espacio.xs),
            Expanded(
              child: Text(
                'Te mostramos tu último Reino guardado. $mensaje',
                style: context.textos.bodySmall?.copyWith(color: p.textoPrimario),
              ),
            ),
            TextButton(onPressed: alReintentar, child: const Text('Reintentar')),
          ],
        ),
      ),
    );
  }
}

/// Error sin nada en caché: la pantalla completa ofrece reintentar.
class _ErrorDelPanel extends StatelessWidget {
  const _ErrorDelPanel({required this.error, required this.alReintentar});

  final ErrorAtenea? error;
  final VoidCallback alReintentar;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: Espacio.xxl),
      child: EstadoError(
        titulo: 'El Reino no responde',
        mensaje: error?.mensaje ??
            'No pudimos traer tu panel. Comprueba tu conexión e inténtalo de nuevo.',
        alReintentar: alReintentar,
      ),
    );
  }
}

/// Fila de medallones con el resumen de la semana.
class _ResumenSemana extends StatelessWidget {
  const _ResumenSemana({
    required this.semana,
    required this.alVerPerfil,
    required this.alVerLogros,
  });

  final EstadisticasSemana semana;
  final VoidCallback alVerPerfil;
  final VoidCallback alVerLogros;

  @override
  Widget build(BuildContext context) {
    // `IntrinsicHeight` no es adorno: sin él, esta fila rompía la pantalla.
    //
    // Los tres medallones deben medir lo mismo aunque uno lleve dos líneas de
    // etiqueta, y eso lo da `CrossAxisAlignment.stretch`. Pero un `ListView` da
    // a sus hijos altura **sin límite**, y `stretch` se la pasa entera a los
    // suyos: `h=Infinity`. En depuración salta una aserción; en release no hay
    // aserciones, así que la fila se estiraba de verdad y el `ListView` creía
    // que su contenido medía una barbaridad. Inicio se desplazaba sin acabar
    // nunca, con media pantalla en blanco al final.
    //
    // `IntrinsicHeight` mide antes a los tres y acota la fila al más alto, que
    // es justo lo que `stretch` necesita para significar algo aquí.
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Expanded(
            child: FichaMedallon(
              tipo: Medallon.tiempo,
              valor: tiempoLegible(semana.segundosActivos),
              etiqueta: 'De estudio',
              alTocar: alVerPerfil,
            ),
          ),
          const SizedBox(width: Espacio.sm),
          Expanded(
            child: FichaMedallon(
              tipo: Medallon.dominio,
              valor: '${semana.lecciones}',
              etiqueta: semana.lecciones == 1 ? 'Lección' : 'Lecciones',
              alTocar: alVerPerfil,
            ),
          ),
          const SizedBox(width: Espacio.sm),
          Expanded(
            child: FichaMedallon(
              tipo: Medallon.nivel,
              valor: '${semana.logros}',
              etiqueta: semana.logros == 1 ? 'Logro' : 'Logros',
              alTocar: alVerLogros,
            ),
          ),
        ],
      ),
    );
  }
}

/// Cierre con anticipación: por qué conviene volver mañana.
class _CierreDelDia extends StatelessWidget {
  const _CierreDelDia({required this.racha, required this.objetivo});

  final Racha racha;
  final ObjetivoDiario objetivo;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final HitoRacha? hito = racha.proximoHito;

    final String texto;
    if (hito != null && hito.faltan > 0) {
      final String premio = hito.recompensa?.resumen ?? '';
      texto = hito.faltan == 1
          ? 'Un día más y alcanzas ${hito.titulo ?? '${hito.dias} días de racha'}'
              '${premio.isEmpty ? '.' : ' · $premio.'}'
          : 'Te faltan ${hito.faltan} días para '
              '${hito.titulo ?? '${hito.dias} días de racha'}'
              '${premio.isEmpty ? '.' : ' · $premio.'}';
    } else if (objetivo.cumplido) {
      texto = 'Hoy ya cumpliste. Vuelve mañana y la racha sigue viva.';
    } else if (racha.actual == 0) {
      texto = 'Hoy empieza tu racha. Una lección basta.';
    } else {
      texto = 'Cuida tu racha: aún estás a tiempo de que hoy cuente.';
    }

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Icon(
          Icons.local_fire_department_rounded,
          size: Tipo.cuerpo,
          color: p.brasa,
        ),
        const SizedBox(width: Espacio.xs),
        Expanded(
          child: Text(
            texto,
            style: context.textos.bodyMedium?.copyWith(color: p.textoSecundario),
          ),
        ),
      ],
    );
  }
}

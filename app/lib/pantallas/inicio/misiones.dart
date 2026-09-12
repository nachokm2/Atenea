/// P19 · Misiones: metas cortas que siempre pasan por aprender.
///
/// Tres horizontes (diarias, semanales y de ruta), el progreso de cada una,
/// su recompensa y el tiempo que falta para el reinicio de medianoche local.
/// Las recompensas las otorga el servidor al cumplir; el botón "Reclamar"
/// solo aparece en las plantillas que exigen reclamo explícito, y su recibo
/// se encola en la cola de celebraciones.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../datos/repositorios.dart';
import '../../design/components.dart';
import '../../design/theme.dart';
import '../../design/tokens.dart';
import '../../estado/celebraciones.dart';
import '../../estado/gamificacion.dart';
import '../../estado/panel.dart';
import '../../navegacion/armazon.dart';
import '../../navegacion/rutas.dart';
import 'widgets/esqueletos.dart';
import 'widgets/formatos.dart';
import 'widgets/tarjeta_mision.dart';

/// Misiones diarias, semanales y de ruta.
class PantallaMisiones extends StatefulWidget {
  const PantallaMisiones({super.key});

  @override
  State<PantallaMisiones> createState() => _PantallaMisionesState();
}

class _PantallaMisionesState extends State<PantallaMisiones> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((Duration _) {
      if (!mounted) return;
      context.read<ControladorGamificacion>().cargarMisiones();
    });
  }

  Future<void> _reclamar(Mision mision) async {
    final ControladorGamificacion gami = context.read<ControladorGamificacion>();
    final ColaCelebraciones cola = context.read<ColaCelebraciones>();
    final ControladorPanel panel = context.read<ControladorPanel>();
    final ReciboRecompensas? recibo = await gami.reclamarMision(mision.id);
    if (!mounted) return;
    if (recibo != null) {
      cola.encolar(recibo);
      unawaited(panel.refrescar());
    }
  }

  Future<void> _abrirDetalle(Mision mision) async {
    final String? destino = await mostrarHoja<String>(
      context,
      constructor: (BuildContext hoja) => _DetalleMision(mision: mision),
    );
    if (!mounted || destino == null || destino.isEmpty) return;
    context.push(destino);
  }

  @override
  Widget build(BuildContext context) {
    final ControladorGamificacion gami = context.watch<ControladorGamificacion>();
    final Misiones? misiones = gami.misiones;
    final List<Mision> visibles = gami.misionesVisibles;

    return PantallaAtenea(
      titulo: 'Misiones',
      mostrarVolver: true,
      cuerpo: RefreshIndicator(
        onRefresh: () => gami.cargarMisiones(forzar: true),
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.only(top: Espacio.xs, bottom: Espacio.xxl),
          children: <Widget>[
            _Pestanas(
              activa: gami.pestanaMisiones,
              alCambiar: gami.fijarPestanaMisiones,
            ),
            const SizedBox(height: Espacio.md),
            if (gami.cargandoMisiones && misiones == null)
              const ListaEsqueleto(filas: 3, lineas: 3, conMedallon: false)
            else if (gami.errorMisiones != null && misiones == null)
              Padding(
                padding: const EdgeInsets.only(top: Espacio.xl),
                child: EstadoError(
                  titulo: 'No pudimos traer tus misiones',
                  mensaje: gami.errorMisiones!.mensaje,
                  alReintentar: () => gami.cargarMisiones(forzar: true),
                ),
              )
            else if (visibles.isEmpty)
              _VacioDePestana(
                ambito: gami.pestanaMisiones,
                alIrAlInicio: () => context.go(Rutas.inicio),
              )
            else ...<Widget>[
              if (gami.pestanaMisiones == AmbitoMision.diaria &&
                  (misiones?.todasCumplidas ?? false))
                const _TodasCumplidas(),
              for (final Mision mision in visibles) ...<Widget>[
                TarjetaMision(
                  mision: mision,
                  reclamando: gami.misionReclamando == mision.id,
                  alReclamar: mision.sePuedeReclamar
                      ? () => _reclamar(mision)
                      : null,
                  alTocar: () => _abrirDetalle(mision),
                ),
                const SizedBox(height: Espacio.sm),
              ],
            ],
            if (gami.errorMisiones != null && misiones != null) ...<Widget>[
              const SizedBox(height: Espacio.xs),
              Text(
                gami.errorMisiones!.mensaje,
                style: context.textos.bodySmall?.copyWith(
                  color: context.paleta.error,
                ),
                textAlign: TextAlign.center,
              ),
            ],
            const SizedBox(height: Espacio.md),
            if (misiones != null)
              _Reinicio(
                segundos: gami.segundosParaReinicio,
                ambito: gami.pestanaMisiones,
              ),
          ],
        ),
      ),
    );
  }
}

/// Selector de horizonte.
class _Pestanas extends StatelessWidget {
  const _Pestanas({required this.activa, required this.alCambiar});

  final AmbitoMision activa;
  final ValueChanged<AmbitoMision> alCambiar;

  @override
  Widget build(BuildContext context) {
    return SegmentedButton<AmbitoMision>(
      segments: <ButtonSegment<AmbitoMision>>[
        for (final AmbitoMision ambito in AmbitoMision.values)
          ButtonSegment<AmbitoMision>(
            value: ambito,
            label: Text(ambito.etiqueta),
          ),
      ],
      selected: <AmbitoMision>{activa},
      showSelectedIcon: false,
      onSelectionChanged: (Set<AmbitoMision> elegido) =>
          alCambiar(elegido.first),
    );
  }
}

/// Banda de celebración cuando el día está completo.
class _TodasCumplidas extends StatelessWidget {
  const _TodasCumplidas();

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    return Padding(
      padding: const EdgeInsets.only(bottom: Espacio.sm),
      child: TarjetaAtenea(
        colorBorde: p.exito,
        hijo: Row(
          children: <Widget>[
            Icon(Icons.military_tech_rounded, color: p.exito, size: Tipo.titulo),
            const SizedBox(width: Espacio.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    'Misiones del día cumplidas',
                    style: context.textos.titleMedium,
                  ),
                  Text(
                    'Mañana hay más. Lo que sigas haciendo hoy es puro avance.',
                    style: context.textos.bodyMedium?.copyWith(
                      color: p.textoSecundario,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Estado vacío por pestaña.
class _VacioDePestana extends StatelessWidget {
  const _VacioDePestana({required this.ambito, required this.alIrAlInicio});

  final AmbitoMision ambito;
  final VoidCallback alIrAlInicio;

  @override
  Widget build(BuildContext context) {
    final (String titulo, String mensaje) = switch (ambito) {
      AmbitoMision.diaria => (
          'Sin misiones por hoy',
          'El Reino te asignará nuevas misiones en el próximo amanecer.',
        ),
      AmbitoMision.semanal => (
          'Aún no hay misiones semanales',
          'Llegarán cuando lleves varios días seguidos de estudio.',
        ),
      AmbitoMision.especial => (
          'Sin misiones de ruta',
          'Cuando avances en una Ruta aparecerán encargos propios de ella.',
        ),
    };

    return Padding(
      padding: const EdgeInsets.only(top: Espacio.xl),
      child: EstadoVacio(
        icono: Icons.flag_outlined,
        titulo: titulo,
        mensaje: mensaje,
        textoAccion: 'Ir al Inicio',
        alTocarAccion: alIrAlInicio,
      ),
    );
  }
}

/// Pie con la cuenta atrás del reinicio.
///
/// El reloj no inventa la hora del reinicio: deja correr la cuenta que llegó
/// en `resets_in_seconds` y vuelve a anclarse cada vez que el servidor la
/// actualiza. Solo se repinta este pie, no la lista entera.
class _Reinicio extends StatefulWidget {
  const _Reinicio({required this.segundos, required this.ambito});

  final int segundos;
  final AmbitoMision ambito;

  @override
  State<_Reinicio> createState() => _ReinicioState();
}

class _ReinicioState extends State<_Reinicio> {
  Timer? _reloj;
  late DateTime _ancla = DateTime.now();

  @override
  void initState() {
    super.initState();
    _reloj = Timer.periodic(const Duration(seconds: 1), (Timer _) {
      if (mounted) setState(() {});
    });
  }

  @override
  void didUpdateWidget(covariant _Reinicio anterior) {
    super.didUpdateWidget(anterior);
    if (anterior.segundos != widget.segundos) _ancla = DateTime.now();
  }

  @override
  void dispose() {
    _reloj?.cancel();
    super.dispose();
  }

  int get _restante {
    final int transcurridos = DateTime.now().difference(_ancla).inSeconds;
    final int falta = widget.segundos - transcurridos;
    return falta < 0 ? 0 : falta;
  }

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final String que = switch (widget.ambito) {
      AmbitoMision.diaria => 'Se reinician',
      AmbitoMision.semanal => 'La semana cierra',
      AmbitoMision.especial => 'Se revisan',
    };
    final String falta = cuentaAtras(_restante);

    return Semantics(
      label: '$que en $falta',
      child: ExcludeSemantics(
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: <Widget>[
            Icon(
              Icons.schedule_rounded,
              size: Tipo.cuerpo,
              color: p.textoSecundario,
            ),
            const SizedBox(width: Espacio.xs),
            Text(
              '$que en ',
              style: context.textos.bodyMedium?.copyWith(
                color: p.textoSecundario,
              ),
            ),
            Text(
              falta,
              style: Cifras.pequena(context).copyWith(color: p.textoPrimario),
            ),
          ],
        ),
      ),
    );
  }
}

/// Hoja de detalle: qué pide la misión y qué hacer ahora mismo.
class _DetalleMision extends StatelessWidget {
  const _DetalleMision({required this.mision});

  final Mision mision;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final String? destino =
        EnlacesProfundos.aDireccionInterna(mision.enlaceProfundo);

    return SafeArea(
      top: false,
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(Espacio.md),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Center(
              child: Container(
                width: Espacio.xxl,
                height: Espacio.xxs,
                decoration: BoxDecoration(
                  color: p.borde,
                  borderRadius: Redondeo.rPildora,
                ),
              ),
            ),
            const SizedBox(height: Espacio.md),
            Row(
              children: <Widget>[
                Pildora(texto: mision.ambito.etiqueta, icono: Icons.flag_rounded),
                const SizedBox(width: Espacio.xs),
                Pildora(
                  texto: mision.estado.etiqueta,
                  color: mision.estaCumplida ? p.exito : p.textoSecundario,
                ),
              ],
            ),
            const SizedBox(height: Espacio.sm),
            Text(mision.titulo, style: context.textos.headlineSmall),
            if (mision.descripcion != null) ...<Widget>[
              const SizedBox(height: Espacio.xs),
              Text(
                mision.descripcion!,
                style: context.textos.bodyLarge?.copyWith(
                  color: p.textoSecundario,
                ),
              ),
            ],
            const SizedBox(height: Espacio.md),
            BarraProgreso(
              valor: mision.fraccion,
              etiqueta: 'Progreso',
              color: mision.estaCumplida ? p.exito : p.arcano,
              textoDerecha: '${mision.progreso}/${mision.meta}',
            ),
            const SizedBox(height: Espacio.md),
            FilaDato(
              icono: Medallon.xp.icono,
              etiqueta: 'Recompensa',
              valor: mision.recompensaLegible.isEmpty
                  ? 'Avance en tu Reino'
                  : mision.recompensaLegible,
            ),
            if (mision.expiraEn != null)
              FilaDato(
                icono: Icons.event_rounded,
                etiqueta: 'Disponible hasta',
                valor: fechaLarga(mision.expiraEn!),
              ),
            if (mision.completadaEn != null)
              FilaDato(
                icono: Icons.check_circle_rounded,
                etiqueta: 'Cumplida',
                valor: fechaLarga(mision.completadaEn!),
              ),
            const SizedBox(height: Espacio.md),
            if (destino != null && !mision.estaCumplida)
              BotonPrimario(
                texto: mision.accionSugerida ?? 'Ir a cumplirla',
                icono: Icons.play_arrow_rounded,
                alTocar: () => Navigator.of(context).pop(destino),
              )
            else
              Text(
                mision.estaCumplida
                    ? 'Ya está cumplida. El Reino registró tu recompensa.'
                    : 'Avanza en cualquier lección y esta misión subirá sola.',
                textAlign: TextAlign.center,
                style: context.textos.bodyMedium?.copyWith(
                  color: p.textoSecundario,
                ),
              ),
          ],
        ),
      ),
    );
  }
}
